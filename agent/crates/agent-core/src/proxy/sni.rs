//! Parse TLS ClientHello Server Name Indication (SNI) from raw bytes.
//!
//! Used by the transparent proxy to classify outbound TLS without decrypting.

/// Extract the SNI hostname from a TLS ClientHello record (peek buffer).
pub fn parse_sni_from_client_hello(data: &[u8]) -> Option<String> {
    // TLS record header: type(1) + version(2) + length(2)
    if data.len() < 5 || data[0] != 0x16 {
        return None;
    }
    let record_len = u16::from_be_bytes([data[3], data[4]]) as usize;
    if data.len() < 5 + record_len {
        return None;
    }
    let handshake = &data[5..5 + record_len];
    parse_client_hello(handshake)
}

fn parse_client_hello(handshake: &[u8]) -> Option<String> {
    // Handshake: type(1) + length(3) + client_version(2) + random(32) + ...
    if handshake.len() < 4 || handshake[0] != 0x01 {
        return None;
    }
    let hs_len = u32::from_be_bytes([0, handshake[1], handshake[2], handshake[3]]) as usize;
    if handshake.len() < 4 + hs_len {
        return None;
    }
    let mut pos = 4 + 2 + 32; // skip version + random
    if pos >= handshake.len() {
        return None;
    }

    // Session ID
    let session_id_len = handshake[pos] as usize;
    pos += 1 + session_id_len;

    // Cipher suites
    if pos + 2 > handshake.len() {
        return None;
    }
    let cipher_len = u16::from_be_bytes([handshake[pos], handshake[pos + 1]]) as usize;
    pos += 2 + cipher_len;

    // Compression methods
    if pos >= handshake.len() {
        return None;
    }
    let comp_len = handshake[pos] as usize;
    pos += 1 + comp_len;

    // Extensions
    if pos + 2 > handshake.len() {
        return None;
    }
    let ext_total = u16::from_be_bytes([handshake[pos], handshake[pos + 1]]) as usize;
    pos += 2;
    let ext_end = pos + ext_total;
    if ext_end > handshake.len() {
        return None;
    }

    while pos + 4 <= ext_end {
        let ext_type = u16::from_be_bytes([handshake[pos], handshake[pos + 1]]);
        let ext_len = u16::from_be_bytes([handshake[pos + 2], handshake[pos + 3]]) as usize;
        pos += 4;
        if pos + ext_len > ext_end {
            break;
        }
        if ext_type == 0x0000 {
            return parse_server_name_ext(&handshake[pos..pos + ext_len]);
        }
        pos += ext_len;
    }
    None
}

fn parse_server_name_ext(ext: &[u8]) -> Option<String> {
    if ext.len() < 2 {
        return None;
    }
    let list_len = u16::from_be_bytes([ext[0], ext[1]]) as usize;
    if ext.len() < 2 + list_len {
        return None;
    }
    let mut pos = 2;
    let list_end = 2 + list_len;
    while pos + 3 <= list_end {
        let name_type = ext[pos];
        let name_len = u16::from_be_bytes([ext[pos + 1], ext[pos + 2]]) as usize;
        pos += 3;
        if pos + name_len > list_end {
            break;
        }
        if name_type == 0 {
            return std::str::from_utf8(&ext[pos..pos + name_len])
                .ok()
                .map(|s| s.to_ascii_lowercase());
        }
        pos += name_len;
    }
    None
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_sni_from_sample_client_hello() {
        // Minimal synthetic ClientHello with SNI "chatgpt.com"
        let mut hs = Vec::new();
        hs.push(0x01); // ClientHello
        hs.extend_from_slice(&[0, 0, 50]); // length placeholder
        hs.extend_from_slice(&[0x03, 0x03]); // TLS 1.2
        hs.extend_from_slice(&[0u8; 32]); // random
        hs.push(0); // session id len
        hs.extend_from_slice(&[0, 2, 0x00, 0x2f]); // cipher suites
        hs.push(1); // compression
        hs.push(0);

        let mut ext = Vec::new();
        // server_name extension
        ext.extend_from_slice(&[0, 0]); // type
        let mut sni = Vec::new();
        sni.extend_from_slice(&[0, (b"chatgpt.com".len() + 3) as u8]);
        sni.push(0); // host_name
        sni.extend_from_slice(&[(b"chatgpt.com".len() >> 8) as u8, b"chatgpt.com".len() as u8]);
        sni.extend_from_slice(b"chatgpt.com");
        ext.extend_from_slice(&[(sni.len() >> 8) as u8, sni.len() as u8]);
        ext.extend_from_slice(&sni);
        hs.extend_from_slice(&[(ext.len() >> 8) as u8, ext.len() as u8]);
        hs.extend_from_slice(&ext);
        // Fix handshake length
        let hs_body_len = hs.len() - 4;
        hs[1] = ((hs_body_len >> 16) & 0xff) as u8;
        hs[2] = ((hs_body_len >> 8) & 0xff) as u8;
        hs[3] = (hs_body_len & 0xff) as u8;

        let mut record = Vec::new();
        record.push(0x16);
        record.extend_from_slice(&[0x03, 0x01]);
        record.extend_from_slice(&[(hs.len() >> 8) as u8, hs.len() as u8]);
        record.extend_from_slice(&hs);

        assert_eq!(
            parse_sni_from_client_hello(&record).as_deref(),
            Some("chatgpt.com")
        );
    }
}
