# Changelog

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project uses [semantic versioning](https://semver.org/).

## [Unreleased]

### Added
- A **Help** page, *How to use Lab Stocks*: the habits that keep the tube and the record in step, finding
  something, the steps for each kind of record, boxes and places, labels, ordering, photos and files, the
  notebook and the editor, setting up eLabJournal, and putting mistakes right. Linked from the top bar, and
  from About, and from an empty list.
- **About** says much more: what each kind of record holds, how the codes are made, how the tools fit
  together, who sees what, what eLab does, and where the data is kept.

### Fixed
- About said a lab's stocks are not seen by other labs. The other labs of its chair group do see them,
  read-only, as the code has always had it.

## [0.12.0] - 2026-10-30

### Changed
- Dates are written day-first, as in Europe: 30-10-2026, and 30-10-2026 16:40 on the 24-hour clock: when a
  glycerol stock was made, plant material collected, an antibody ordered, an order asked for, ordered and
  received, who made or changed a record when, and on labels. Stored dates stay as they were (2026-10-30).

## [0.11.0] - 2026-10-26

### Added
- Word, PowerPoint and Excel files on a glycerol stock, primer, chemical or antibody open in the browser, without downloading: old and new
  formats (.doc, .docx, .ppt, .pptx, .xls, .xlsx), OpenDocument, RTF and CSV are turned into a PDF by the suite's
  converter (`CONVERTER_URL`) the first time they are opened, and the PDF is kept for the next time. Text files
  (notes, FASTA, GenBank) open as plain text. The original still downloads. Without a converter, office files
  download as before.

## [0.10.0] - 2026-10-26

### Added
- **The lab's own people in eLab** (the lab admin, in Bring over from eLab): tick which of eLab's owners are the
  lab's own, each with their account here if they have one. What they own in eLab is credited to them; what anyone
  else owns, in a group shared with other labs, is credited to the administrator (`ELAB_OTHERS_BY`, default
  `admin`). Every stock and tube brought over keeps its owner in eLab, shown on its page as "Owner in eLab"
  when someone else is credited. Saving credits what is here again at once, and the hourly look at eLab's
  owners keeps it so. With none ticked, each is credited to its owner in eLab, as before.

### Fixed
- Bringing over a glycerol stock or tube that eLab keeps in a compartment without a place in it (position -1
  there) stopped its batch with "A storage location in eLab is chosen from the list".

## [0.9.0] - 2026-10-26

### Added
- **⇧ Update from eLab** (for the lab admin, beside Send now): takes what was changed in eLab since it was
  last sent, for every glycerol stock and tube linked to a sample there: a glycerol stock's fields (strain,
  host system, markers, permit, biosafety, inserts, gene IDs, donor, harmful), where it is kept in eLab's
  storage, and the name of one brought over from eLab. Where both were changed, eLab is right; what was
  changed only here stays, and is sent at the next round. Each change is in the history ("changed in eLab").
  It runs only when pressed.

## [0.8.0] - 2026-10-26

### Fixed
- Bringing over many glycerol stocks or tubes from eLab at once could stop part way (the server gives a
  request two minutes), leaving them made here but not linked to their samples. Each round then tried to
  make them in eLab, which said "There is no free space at position … in storage layer #…". Now:
  - they are brought over 25 at a time, each batch linked as it is made;
  - a round finding a stock's place in eLab taken by an unlinked sample of its name links it to that
    sample instead of making it (so those left unlinked mend themselves at the next round);
  - bringing over again links what a stopped bringing over left, rather than making it twice;
  - one brought over is marked so, and is never made in eLab: linked again to its sample if its link is
    lost.

### Changed
- What is brought over from eLab is made by its owner in eLab, not by who brought it over (the history
  still says who did). eLab is right: the owners are looked up every hour, and on opening Bring over,
  and corrected here when they differ, in the history too. Those made here and sent to eLab keep their maker.

### Added
- Bringing over from eLab shows a progress bar: how many samples are done of how many.

## [0.7.0] - 2026-10-24

### Added
- A glycerol stock's **Family tree ↗**: in the Seed Bank, the lines made with its plasmid, their seeds and plants.

## [0.6.0] - 2026-10-23

### Changed
- **Trellis Tools' look**: the header every module shares (Trellis Tools, then this module's icon and name,
  its tabs, the person and Log out), and the suite's palette - green for what you do, brown for structure,
  on warm paper-white - from static/trellis/trellis.css, copied in from the suite (design/sync.sh).
- Trellis Tools' small icons instead of emoji: the kinds of stock, orders, boxes of tubes, safety links (SOFOS,
  Chemwatch), labels, files and plasmids.

## [0.5.3] - 2026-10-23

### Changed
- The suite it runs in is called Trellis Tools, as its About page now say.

## [0.5.2] - 2026-10-23

### Changed
- Someone who has left (archived in the suite) is no longer offered in lists of people; their records stay.

## [0.5.1] - 2026-10-23

### Changed
- Label QR codes open the suite's public address as an administrator set it on the suite dashboard's
  Hosting tab; SUITE_PUBLIC_URL counts until they do.

## [0.5.0] - 2026-10-23

### Changed
- A tick in the header of each list chooses every stock it shows (what a search has left) for labels,
  or none; it is half-ticked when only some are chosen.
- The labels page shows and prints the labels as the LabTAG DYMO label chosen, in place of its three
  generic sizes.

### Added
- **Labels for the DYMO LabelWriter, on LabTAG labels.** On the labels page, choose a LabTAG DYMO
  label - the LWCS labels made for the LabelWriter 550, or the DY4 range on LabTAG's DYMO-compatible
  templates page. The page shows the labels as they will print on it, 🖨 Print prints them one to a
  page of the label's size, and ⬇ DYMO files (for the region DYMO Connect is set to) downloads a zip
  for DYMO Connect. The zip holds a ready
  .dymo file for each printed label, to open and print in DYMO Connect, and a design with the labels
  as a spreadsheet, to print many at once with Import data. Each sticker gets its code and lines
  (shrunk to fit) and a QR code where it has room; a cap circle or strip gets the short code; labels
  with several stickers (2 up, dots, tags) are filled in order. The LWCS labels have no published
  template: they are laid out as the DY4 label of the same size, and DYMO Connect takes the roll in
  the printer.

## [0.4.3] - 2026-10-21

### Changed
- Bring over from eLab: everyone owning samples of the kind in eLab stays listed, also when all of
  theirs are here already (greyed, saying how many are here, with nothing to tick).

### Added
- For the Seed Bank: how far a lab's seed lots are copied to eLab, a lot's sample and state there,
  and sending a lot now (or again, when archived in eLab).

## [0.4.2] - 2026-10-20

### Changed
- The order list: everyone in a lab sees the lab's orders, and those of the other labs of its chair
  group (marked with their lab), so the group sees what is asked for already; no other lab sees
  them. Each lab's own lab admins still handle its orders, and their spreadsheet holds only those.

## [0.4.1] - 2026-10-20

### Added
- A primer's 5′ and 3′ modifications, as oligo suppliers offer them (Phosphate, Biotin, 6-FAM, HEX,
  Cy3, Cy5, amino and thiol linkers, BHQ quenchers, Inverted dT, ...; others may be typed), beside
  other (internal) modifications. Its order says it as suppliers want it:
  5′-[6-FAM]GTAAAACGACGGCCAGT[BHQ-1]-3′ (17 nt). Shown on its page, in the list and on labels,
  and searched.

## [0.4.0] - 2026-10-20

### Added

- Copies a lab's glycerol stocks, and its seed lots from the Seed Bank, to
  eLabJournal's inventory, one way, into the eLab group's own sample types
  (Glycerol Stock, Plant Seed) and the fields they have, adding nothing to them;
  archived there when used up, discarded or deleted. The lab admin connects it
  with *Connect to eLabJournal…*, which walks them through making a token in
  eLab, tries it, and lets them choose the sample types and the lab's permit and
  biosafety level. The list pages say how far the copy is.
- A glycerol stock's biosafety, as the GMO register (and eLab's Glycerol Stock type) asks: permit,
  biosafety level and host system (empty: the lab's, or from the strain), plant and yeast markers,
  insert(s), gene IDs, donor organism(s), harmful gene product and remarks on it; added to existing
  databases. eLab also gets the sequence and size of the plasmid linked in the editor, and from a
  Seed Bank 0.4.0 on, a seed lot's line's biosafety, stock center and genetics.
- A glycerol stock's storage location in eLab, chosen in its form from the group's storage (its
  freezers' towers, shelves and boxes, and a place in a box), or added there from the form; its
  sample in eLab is put there, and moved with it.
- Plant material: tubes kept for later processing, a box of them at once (numbered, or a pasted
  list) filling a box's places in eLab, linked from the notebook by code, copied to eLab's Plant
  Material type.
- A record's page links to its sample in eLab and says how it stands there; one archived in eLab can
  be sent again (to the same sample once restored there, else a new one).
- Nothing is made twice in eLab: records found again by code or name, a taken code reported rather
  than sent again, seed lots brought over only ever linked, an eLab sample linked to one record.
- Bringing over what eLab already has: its plant material as tubes here, and its seed samples to
  the Seed Bank as lines and lots, each linked to its sample, which keeps its name there.
- Chair groups, as the suite's administrators set them on the dashboard (suite 2.9.0 on): their
  labs see each other's stocks, read-only, on request in the lists.

## [0.3.0] - 2026-10-19

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
  🛒 Add to order on a chemical, primer or antibody (its details go along, and it is not added twice),
  or, for primers, by ticking them in the list and 🛒 Add selected to order.
  A chemical switched to Out is added by itself. The lab's lab admins see that lab's orders only,
  with the number waiting on the Orders tab, and mark each ordered, received or cancelled; a stock
  that had run out is in stock again when its order is received. The list downloads as a
  spreadsheet, with primers' sequences in a column of their own. Stocks on order are marked 🛒 in
  their lists. Others see their own requests, and can change or cancel them until they are ordered.

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
