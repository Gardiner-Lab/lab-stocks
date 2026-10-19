# Changelog

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project uses [semantic versioning](https://semver.org/).

## [Unreleased]

### Added
- **Chemicals**, a third list beside glycerol stocks and primers: name, CAS number (its check digit
  is checked), room, size, status and notes, numbered like the others (`GL-C-0003`) and on labels.
  A chemical's page holds its safety data sheet (a PDF, marked 📕 in the list) and links to the
  university's SOFOS register and to Chemwatch, with the CAS number ready to copy. The links can be
  changed with `SOFOS_URL` and `CHEMWATCH_URL`.
  An **Out** switch, in the list and on its page, marks a chemical that has run out (it is greyed
  in the list) and back in stock. Chemicals can be linked from the Lab Notebook, like other stocks.
- **Antibodies**, a fourth list (`GL-A-0005`): the short code the lab calls it, a description,
  primary, secondary or other, producer, source animal, product number and notes about the use,
  with status, photos and files, labels and links from the Lab Notebook.
- **Orders**, the lab's order list. Anyone in a lab asks for something with ＋ Order request, or with
  🛒 Add to order on a chemical, primer or antibody (its details go along, and it is not added twice).
  A chemical switched to Out is added by itself. The lab's lab admins see that lab's orders only,
  with the number waiting on the Orders tab, and mark each ordered, received or cancelled; a stock
  that had run out is in stock again when its order is received. The list downloads as a
  spreadsheet. Others see their own requests, and can change or cancel them until they are ordered.

## [0.2.0] - 2026-10-19

### Changed
- People can be in several labs: they see the stocks of all of them, and choose which lab a new stock
  goes to (a picker at the top, for someone in more than one; their first lab until they choose). A
  lab's code is chosen by that lab's lead.
- Plasmids follow the Plasmid Editor: always the owner's labs', every lab's once public.

## [0.1.2] - 2026-10-16

### Added
- **A glycerol stock's plasmid, one click away.** 🧬 Open in the Plasmid Editor, at the top of a
  stock, opens the plasmid it holds.
- **Linking a stock to its plasmid afterwards**: 🔗 Link a plasmid… on a stock not linked to one
  (made with only a plasmid's name), and 🔗 Change plasmid… to link it to another, from the editor's
  library. The stock takes the plasmid's name there, and the change is in its history.
- A stock says so when its plasmid cannot be opened: no longer in the editor's library, or in
  someone's own plasmids, not shared, instead of a link that goes nowhere.

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
