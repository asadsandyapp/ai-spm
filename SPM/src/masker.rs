use regex::Regex;
use std::sync::LazyLock;

/// Replacement token used for every detected email address.
pub const EMAIL_REDACTED: &str = "[EMAIL_REDACTED]";

/// Compiled once at startup. Matches standard email addresses including multi-part TLDs.
static EMAIL_REGEX: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(
        r"(?i)\b[a-z0-9._%+-]+@[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)+\b",
    )
    .expect("email regex must compile")
});

/// Count email addresses in `text` without modifying it.
pub fn count_emails(text: &str) -> usize {
    EMAIL_REGEX.find_iter(text).count()
}

/// Replace every email address in `text` with [`EMAIL_REDACTED`].
pub fn mask_emails(text: &str) -> String {
    EMAIL_REGEX
        .replace_all(text, EMAIL_REDACTED)
        .into_owned()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn masks_single_email() {
        assert_eq!(mask_emails("john@gmail.com"), EMAIL_REDACTED);
    }

    #[test]
    fn masks_multi_part_tld() {
        assert_eq!(mask_emails("support@company.co.uk"), EMAIL_REDACTED);
    }

    #[test]
    fn masks_multiple_emails() {
        let input = "Contact me:\njohn@gmail.com\nor\nalice@yahoo.com";
        let expected = format!(
            "Contact me:\n{EMAIL_REDACTED}\nor\n{EMAIL_REDACTED}"
        );
        assert_eq!(mask_emails(input), expected);
    }

    #[test]
    fn counts_without_masking() {
        let input = "a@b.com and c@d.org";
        assert_eq!(count_emails(input), 2);
    }
}
