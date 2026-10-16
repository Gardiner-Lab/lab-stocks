# Changelog

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project uses [semantic versioning](https://semver.org/).

## [Unreleased]

## [0.1.1] - 2026-10-16

### Fixed
- **Copy buttons work over plain http.** Browsers allow the clipboard API only on secure pages
  (https, or localhost); elsewhere a primer's Copy now copies with the copy command instead, and says so
  when even that is blocked.

## [0.1.0] - 2026-10-15

The first release.

### Added
- Glycerol stocks, numbered per lab and linked to their plasmid. They are made from the Plasmid
  Editor on confirming a plasmid by sequencing.
- Primers with sequence, length, GC and Tm, searchable by sequence. Saved from the editor's primer
  design; the editor finds the ones that bind a plasmid.
- Lab codes shared with the Seed Bank, storage, labels with QR codes, photos and files, links from
  the Lab Notebook. Each lab's stocks are its own.
