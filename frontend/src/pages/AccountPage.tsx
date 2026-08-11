import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { KeyRound, UserRound } from "lucide-react";
import { PageHeader, Spinner, ErrorState } from "@/components/ui/States";
import { adminApi, platformApi, ApiError } from "@/lib/api";
import { queryKeys, useMe, usePlatformMe } from "@/hooks/queries";
import type { AuthScope } from "@/stores/auth";
import { titleCase } from "@/lib/utils";

interface AccountPageProps {
  scope: AuthScope;
}

export function AccountPage({ scope }: AccountPageProps) {
  const qc = useQueryClient();
  const adminMe = useMe(scope === "admin");
  const platformMe = usePlatformMe(scope === "platform");
  const meQuery = scope === "admin" ? adminMe : platformMe;
  const me = meQuery.data;

  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [profileMsg, setProfileMsg] = useState<string | null>(null);
  const [profileErr, setProfileErr] = useState<string | null>(null);

  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [passwordMsg, setPasswordMsg] = useState<string | null>(null);
  const [passwordErr, setPasswordErr] = useState<string | null>(null);

  useEffect(() => {
    if (!me) return;
    setFullName(me.full_name ?? "");
    setEmail(me.email ?? "");
  }, [me]);

  const profileM = useMutation({
    mutationFn: async () => {
      const body = { full_name: fullName.trim(), email: email.trim() };
      if (scope === "admin") {
        return adminApi.updateProfile(body);
      }
      return platformApi.updateProfile(body);
    },
    onSuccess: () => {
      setProfileErr(null);
      setProfileMsg("Profile updated.");
      void qc.invalidateQueries({
        queryKey: scope === "admin" ? queryKeys.me : queryKeys.platformMe,
      });
    },
    onError: (err: unknown) => {
      setProfileMsg(null);
      setProfileErr(err instanceof ApiError ? err.detail : "Unable to update profile.");
    },
  });

  const passwordM = useMutation({
    mutationFn: async () => {
      if (newPassword !== confirmPassword) {
        throw new ApiError(400, "New password and confirmation do not match.");
      }
      if (newPassword.length < 12) {
        throw new ApiError(400, "New password must be at least 12 characters.");
      }
      const body = {
        current_password: currentPassword,
        new_password: newPassword,
      };
      if (scope === "admin") {
        return adminApi.changePassword(body);
      }
      return platformApi.changePassword(body);
    },
    onSuccess: () => {
      setPasswordErr(null);
      setPasswordMsg("Password updated.");
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
    },
    onError: (err: unknown) => {
      setPasswordMsg(null);
      setPasswordErr(
        err instanceof ApiError ? err.detail : "Unable to update password.",
      );
    },
  });

  return (
    <div className="animate-fade-in">
      <PageHeader
        title="Account"
        description="Update your profile details and password."
      />

      {meQuery.isLoading && <Spinner />}
      {meQuery.isError && (
        <ErrorState error={meQuery.error} onRetry={() => meQuery.refetch()} />
      )}

      {me && (
        <div className="mt-6 grid gap-6 lg:grid-cols-2">
          <form
            className="card p-6"
            onSubmit={(e) => {
              e.preventDefault();
              setProfileMsg(null);
              setProfileErr(null);
              profileM.mutate();
            }}
          >
            <div className="mb-5 flex items-center gap-2">
              <UserRound className="h-5 w-5 text-brand-600" />
              <h2 className="text-lg font-semibold text-ink-900">Profile</h2>
            </div>
            <div className="space-y-4">
              <div>
                <label className="label" htmlFor="acct-name">
                  Full name
                </label>
                <input
                  id="acct-name"
                  className="input"
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  required
                  minLength={1}
                />
              </div>
              <div>
                <label className="label" htmlFor="acct-email">
                  Email
                </label>
                <input
                  id="acct-email"
                  type="email"
                  className="input"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                />
              </div>
              <div>
                <p className="label">Role</p>
                <p className="text-sm text-ink-600">{titleCase(me.role)}</p>
              </div>
              {profileErr && (
                <p className="text-sm text-rose-600">{profileErr}</p>
              )}
              {profileMsg && (
                <p className="text-sm text-emerald-700">{profileMsg}</p>
              )}
              <button
                type="submit"
                className="btn-primary"
                disabled={profileM.isPending}
              >
                {profileM.isPending ? "Saving…" : "Save profile"}
              </button>
            </div>
          </form>

          <form
            className="card p-6"
            onSubmit={(e) => {
              e.preventDefault();
              setPasswordMsg(null);
              setPasswordErr(null);
              passwordM.mutate();
            }}
          >
            <div className="mb-5 flex items-center gap-2">
              <KeyRound className="h-5 w-5 text-brand-600" />
              <h2 className="text-lg font-semibold text-ink-900">Password</h2>
            </div>
            <div className="space-y-4">
              <div>
                <label className="label" htmlFor="acct-current">
                  Current password
                </label>
                <input
                  id="acct-current"
                  type="password"
                  className="input"
                  value={currentPassword}
                  onChange={(e) => setCurrentPassword(e.target.value)}
                  required
                  autoComplete="current-password"
                />
              </div>
              <div>
                <label className="label" htmlFor="acct-new">
                  New password
                </label>
                <input
                  id="acct-new"
                  type="password"
                  className="input"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  required
                  minLength={12}
                  autoComplete="new-password"
                />
                <p className="mt-1 text-xs text-ink-500">
                  At least 12 characters.
                </p>
              </div>
              <div>
                <label className="label" htmlFor="acct-confirm">
                  Confirm new password
                </label>
                <input
                  id="acct-confirm"
                  type="password"
                  className="input"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  required
                  minLength={12}
                  autoComplete="new-password"
                />
              </div>
              {passwordErr && (
                <p className="text-sm text-rose-600">{passwordErr}</p>
              )}
              {passwordMsg && (
                <p className="text-sm text-emerald-700">{passwordMsg}</p>
              )}
              <button
                type="submit"
                className="btn-primary"
                disabled={passwordM.isPending}
              >
                {passwordM.isPending ? "Updating…" : "Update password"}
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
