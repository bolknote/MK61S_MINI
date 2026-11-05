#!/usr/bin/env perl

use strict;
use warnings;
use Encode qw(decode encode FB_CROAK);

# Desktop boundary codec for MKC. Device files use M8; files edited on the
# host use strict UTF-8. CP1251-compatible characters retain their byte value,
# while calculator symbols occupy the M8 private C0 range 0x0E..0x1F.

my @private_codepoints = (
    0x2190, 0x2192, 0x2191, 0x2193, 0x03C0, 0x221A,
    0x21BB, 0x2260, 0x2264, 0x2265, 0x00D7, 0x00F7,
    0x00B2, 0x02B8, 0x02E3, 0x22BB, 0x207B, 0x21B5,
);
my %private_bytes = map { $private_codepoints[$_] => 0x0E + $_ }
    0 .. $#private_codepoints;

sub valid_m8_byte {
    my ($byte) = @_;
    return 0 if $byte == 0 || $byte == 0x7F || $byte == 0x98;
    return 1 if $byte == 9 || $byte == 10 || $byte == 13;
    return 1 if $byte >= 0x0E && $byte <= 0x1F;
    return $byte >= 0x20;
}

sub read_all {
    my ($path) = @_;
    local $/;
    if($path eq '-') {
        binmode STDIN;
        my $data = <STDIN>;
        return defined($data) ? $data : '';
    }
    open my $handle, '<:raw', $path or die "cannot read $path: $!\n";
    my $data = <$handle>;
    close $handle or die "cannot close $path: $!\n";
    return defined($data) ? $data : '';
}

sub write_all {
    my ($path, $data) = @_;
    if($path eq '-') {
        binmode STDOUT;
        print STDOUT $data or die "cannot write stdout: $!\n";
        return;
    }
    open my $handle, '>:raw', $path or die "cannot write $path: $!\n";
    print {$handle} $data or die "cannot write $path: $!\n";
    close $handle or die "cannot close $path: $!\n";
}

sub utf8_to_m8 {
    my ($raw) = @_;
    my $text = decode('UTF-8', $raw, FB_CROAK);
    $text =~ s/^\x{FEFF}//;
    my $output = '';
    for my $character (split //, $text) {
        my $codepoint = ord($character);
        if(exists $private_bytes{$codepoint}) {
            $output .= pack('C', $private_bytes{$codepoint});
            next;
        }
        my $encoded = encode('cp1251', $character, FB_CROAK);
        die sprintf("U+%04X is not one M8 byte\n", $codepoint)
            unless length($encoded) == 1;
        my $byte = unpack('C', $encoded);
        die sprintf("U+%04X maps to invalid M8 byte 0x%02X\n",
                    $codepoint, $byte)
            unless valid_m8_byte($byte);
        $output .= $encoded;
    }
    return $output;
}

sub m8_to_utf8 {
    my ($raw) = @_;
    my $text = '';
    for my $byte (unpack('C*', $raw)) {
        die sprintf("invalid M8 byte 0x%02X\n", $byte)
            unless valid_m8_byte($byte);
        if($byte >= 0x0E && $byte <= 0x1F) {
            $text .= chr($private_codepoints[$byte - 0x0E]);
        } else {
            $text .= decode('cp1251', pack('C', $byte), FB_CROAK);
        }
    }
    return encode('UTF-8', $text, FB_CROAK);
}

@ARGV == 3 or die "usage: m8_codec.pl encode|decode INPUT OUTPUT\n";
my ($operation, $input_path, $output_path) = @ARGV;
my $input = read_all($input_path);
my $output = $operation eq 'encode' ? utf8_to_m8($input)
           : $operation eq 'decode' ? m8_to_utf8($input)
           : die "unknown operation: $operation\n";
write_all($output_path, $output);
