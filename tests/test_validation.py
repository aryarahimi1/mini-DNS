"""Unit tests for DNS validation functions."""

import pytest
from app.dns_logic import (
    validate_hostname,
    validate_ipv4_address,
    validate_ipv6_address,
    validate_mx_value,
    validate_txt_value,
)


# ── validate_hostname ──────────────────────────────────────────────


class TestValidateHostname:

    def test_valid_simple_hostname(self):
        assert validate_hostname("example.com") is True

    def test_valid_subdomain(self):
        assert validate_hostname("sub.example.com") is True

    def test_valid_deep_subdomain(self):
        assert validate_hostname("a.b.c.example.com") is True

    def test_valid_with_hyphens(self):
        assert validate_hostname("my-site.example.com") is True

    def test_valid_with_numbers(self):
        assert validate_hostname("server1.example.com") is True

    def test_valid_trailing_dot(self):
        assert validate_hostname("example.com.") is True

    def test_invalid_empty_string(self):
        assert validate_hostname("") is False

    def test_invalid_single_label(self):
        assert validate_hostname("localhost") is False

    def test_invalid_leading_hyphen(self):
        assert validate_hostname("-example.com") is False

    def test_invalid_trailing_hyphen(self):
        assert validate_hostname("example-.com") is False

    def test_invalid_special_characters(self):
        assert validate_hostname("ex@mple.com") is False

    def test_invalid_spaces(self):
        assert validate_hostname("ex ample.com") is False

    def test_invalid_underscore(self):
        assert validate_hostname("ex_ample.com") is False

    def test_invalid_too_long(self):
        long_label = "a" * 63
        hostname = f"{long_label}.{long_label}.{long_label}.{long_label}.com"
        assert validate_hostname(hostname) is False

    def test_valid_max_label_length(self):
        label = "a" * 63
        assert validate_hostname(f"{label}.com") is True

    def test_invalid_label_too_long(self):
        label = "a" * 64
        assert validate_hostname(f"{label}.com") is False


# ── validate_ipv4_address ──────────────────────────────────────────


class TestValidateIPv4:

    def test_valid_ip(self):
        assert validate_ipv4_address("192.168.1.1") is True

    def test_valid_all_zeros(self):
        assert validate_ipv4_address("0.0.0.0") is True

    def test_valid_max_values(self):
        assert validate_ipv4_address("255.255.255.255") is True

    def test_valid_loopback(self):
        assert validate_ipv4_address("127.0.0.1") is True

    def test_invalid_leading_zeros(self):
        assert validate_ipv4_address("01.02.03.04") is False

    def test_invalid_leading_zero_single_octet(self):
        assert validate_ipv4_address("192.168.01.1") is False

    def test_invalid_too_few_octets(self):
        assert validate_ipv4_address("192.168.1") is False

    def test_invalid_too_many_octets(self):
        assert validate_ipv4_address("192.168.1.1.1") is False

    def test_invalid_octet_above_255(self):
        assert validate_ipv4_address("256.0.0.1") is False

    def test_invalid_negative_octet(self):
        assert validate_ipv4_address("-1.0.0.1") is False

    def test_invalid_non_numeric(self):
        assert validate_ipv4_address("abc.def.ghi.jkl") is False

    def test_invalid_empty_string(self):
        assert validate_ipv4_address("") is False

    def test_invalid_hostname_as_ip(self):
        assert validate_ipv4_address("example.com") is False

    def test_invalid_with_spaces(self):
        assert validate_ipv4_address("192.168.1. 1") is False


# ── validate_ipv6_address ──────────────────────────────────────────


class TestValidateIPv6:

    def test_valid_full_address(self):
        assert validate_ipv6_address("2001:0db8:85a3:0000:0000:8a2e:0370:7334") is True

    def test_valid_compressed(self):
        assert validate_ipv6_address("2001:db8::1") is True

    def test_valid_loopback(self):
        assert validate_ipv6_address("::1") is True

    def test_valid_all_zeros(self):
        assert validate_ipv6_address("::") is True

    def test_valid_link_local(self):
        assert validate_ipv6_address("fe80::1") is True

    def test_valid_uppercase(self):
        assert validate_ipv6_address("2001:0DB8::1") is True

    def test_invalid_empty_string(self):
        assert validate_ipv6_address("") is False

    def test_invalid_ipv4(self):
        assert validate_ipv6_address("192.168.1.1") is False

    def test_invalid_too_many_groups(self):
        assert validate_ipv6_address("2001:db8:85a3:0:0:8a2e:370:7334:extra") is False

    def test_invalid_bad_hex(self):
        assert validate_ipv6_address("2001:db8::gggg") is False

    def test_invalid_hostname(self):
        assert validate_ipv6_address("example.com") is False

    def test_invalid_trailing_colon(self):
        assert validate_ipv6_address("2001:db8:") is False


# ── validate_mx_value ──────────────────────────────────────────────


class TestValidateMXValue:

    def test_valid_basic(self):
        assert validate_mx_value("10 mail.example.com") is True

    def test_valid_zero_priority(self):
        assert validate_mx_value("0 mail.example.com") is True

    def test_valid_high_priority(self):
        assert validate_mx_value("65535 backup.mail.example.com") is True

    def test_valid_subdomain_target(self):
        assert validate_mx_value("20 mx1.mail.example.com") is True

    def test_invalid_missing_priority(self):
        assert validate_mx_value("mail.example.com") is False

    def test_invalid_negative_priority(self):
        assert validate_mx_value("-1 mail.example.com") is False

    def test_invalid_priority_too_high(self):
        assert validate_mx_value("65536 mail.example.com") is False

    def test_invalid_non_numeric_priority(self):
        assert validate_mx_value("abc mail.example.com") is False

    def test_invalid_bad_hostname(self):
        assert validate_mx_value("10 !!!invalid!!!") is False

    def test_invalid_empty(self):
        assert validate_mx_value("") is False

    def test_invalid_only_priority(self):
        assert validate_mx_value("10") is False

    def test_invalid_single_label_target(self):
        assert validate_mx_value("10 localhost") is False


# ── validate_txt_value ─────────────────────────────────────────────


class TestValidateTXTValue:

    def test_valid_spf(self):
        assert validate_txt_value("v=spf1 include:_spf.google.com ~all") is True

    def test_valid_verification(self):
        assert validate_txt_value("google-site-verification=abc123def456") is True

    def test_valid_dkim_fragment(self):
        assert validate_txt_value("v=DKIM1; k=rsa; p=MIGfMA0GCSqGS") is True

    def test_valid_short(self):
        assert validate_txt_value("a") is True

    def test_valid_max_length(self):
        assert validate_txt_value("x" * 512) is True

    def test_invalid_empty(self):
        assert validate_txt_value("") is False

    def test_invalid_too_long(self):
        assert validate_txt_value("x" * 513) is False

    def test_invalid_control_characters(self):
        assert validate_txt_value("hello\x00world") is False
