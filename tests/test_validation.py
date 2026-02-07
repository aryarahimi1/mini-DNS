"""Unit tests for DNS validation functions."""

import pytest
from app.dns_logic import validate_hostname, validate_ipv4_address


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
        # 259 characters total exceeds 253 limit
        long_label = "a" * 63
        hostname = f"{long_label}.{long_label}.{long_label}.{long_label}.com"
        assert validate_hostname(hostname) is False

    def test_valid_max_label_length(self):
        # 63-char label is the max allowed
        label = "a" * 63
        assert validate_hostname(f"{label}.com") is True

    def test_invalid_label_too_long(self):
        # 64-char label exceeds limit
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
