import { cn } from "@/lib/utils";

const ENTITY_PREVIEW = 3;
const PROMPT_CHAR_LIMIT = 140;
const PROMPT_WORD_LIMIT = 24;

export function promptIsExpandable(text: string | null | undefined): boolean {
  const value = text?.trim() ?? "";
  if (!value) return false;
  return value.length > PROMPT_CHAR_LIMIT || value.split(/\s+/).length > PROMPT_WORD_LIMIT;
}

export function entitiesAreExpandable(
  entities: string[] | null | undefined,
): boolean {
  return (entities?.length ?? 0) > ENTITY_PREVIEW;
}

/** Compact prompt body — expansion controlled by the parent row. */
export function PromptCell({
  text,
  empty = "—",
  expanded,
  onToggleExpand,
  className,
}: {
  text: string | null | undefined;
  empty?: string;
  expanded: boolean;
  onToggleExpand: () => void;
  className?: string;
}) {
  const value = text?.trim() ?? "";

  if (!value) {
    return <span className="text-ink-400">{empty}</span>;
  }

  const long = promptIsExpandable(value);

  return (
    <div className={cn("min-w-0", className)}>
      <p
        className={cn(
          "break-words text-[13px] leading-relaxed text-ink-700",
          !expanded && "line-clamp-2",
        )}
        title={expanded || !long ? undefined : value}
      >
        {value}
      </p>
      {long && (
        <button
          type="button"
          className="mt-1.5 text-[11px] font-semibold text-brand-700 hover:text-brand-800"
          onClick={onToggleExpand}
        >
          {expanded ? "Show less" : "Show more"}
        </button>
      )}
    </div>
  );
}

/** Amber PII chips — expansion controlled by the parent row. */
export function DetectedCell({
  entities,
  hitCount = 0,
  expanded,
  onToggleExpand,
}: {
  entities: string[] | null | undefined;
  hitCount?: number;
  expanded: boolean;
  onToggleExpand: () => void;
}) {
  const list = entities ?? [];

  if (list.length === 0) {
    return <span className="text-ink-400">—</span>;
  }

  const canExpand = entitiesAreExpandable(list);
  const visible = expanded || !canExpand ? list : list.slice(0, ENTITY_PREVIEW);
  const hidden = list.length - visible.length;

  return (
    <div className="min-w-0">
      <div className="flex flex-wrap gap-1">
        {visible.map((ent) => (
          <span
            key={ent}
            className="inline-flex items-center rounded-md bg-amber-50 px-1.5 py-0.5 font-mono text-[10px] font-semibold tracking-wide text-amber-800 ring-1 ring-amber-600/15"
          >
            {ent}
          </span>
        ))}
        {hidden > 0 && (
          <button
            type="button"
            className="rounded-md bg-ink-100 px-1.5 py-0.5 text-[10px] font-semibold text-ink-600 ring-1 ring-ink-200 hover:bg-ink-200"
            onClick={onToggleExpand}
          >
            +{hidden}
          </button>
        )}
      </div>
      <div className="mt-1.5 flex items-center gap-2">
        {hitCount > 0 && (
          <span className="text-[10px] font-medium tabular-nums text-ink-400">
            {hitCount} hit{hitCount === 1 ? "" : "s"}
          </span>
        )}
        {canExpand && expanded && (
          <button
            type="button"
            className="text-[10px] font-semibold text-brand-700 hover:text-brand-800"
            onClick={onToggleExpand}
          >
            Show less
          </button>
        )}
      </div>
    </div>
  );
}
