# Lab Stocks

The Gardiner Lab suite's glycerol stocks, primers, chemicals and antibodies.

- **Glycerol stocks** are numbered per lab: `GL-G-0042`.
  - Each is linked to the plasmid it holds in the Plasmid Editor's library, and records the clone,
    strain, selection, where it is kept and its status.
  - Confirming a plasmid by sequencing in the Plasmid Editor makes its glycerol stock here, with the
    lab's next number. That number is recorded on the plasmid and in MoClo.
- **Primers** are numbered `GL-O-0007` (O for oligo).
  - Each records its sequence (IUPAC codes allowed), and its length, GC and Tm are worked out
    (nearest neighbour, 50 mM Na⁺, 250 nM). It also records direction, target, purpose,
    modifications, supplier, order date, concentration and where the tube is.
  - Primers can be searched by name or by any piece of their sequence.
  - Primers designed in the editor are saved here with one click, and the editor lists the lab's
    primers that bind a plasmid.
- **Chemicals** are numbered `GL-C-0003`.
  - Each records its name, CAS number (its check digit is checked), the room it is kept in, its size
    and status.
  - An **Out** switch, in the list and on its page, marks one that has run out, and puts it on the
    order list.
  - A chemical's page holds its safety data sheet (SDS, a PDF), and links to the university's
    hazardous substances register (SOFOS) and to Chemwatch, with its CAS number ready to copy.
- **Antibodies** are numbered `GL-A-0005`.
  - Each records the short code the lab calls it, a description, whether it is primary, secondary
    or other, its producer, the animal it is raised in, its product number, and notes about using it.
- **Orders**: the lab's order list.
  - Anyone in a lab asks for something with the order request form (an enzyme, a kit, tips), or
    with 🛒 Add to order on a chemical, primer or antibody, whose details (CAS number, sequence,
    producer and product number) go along. Primers ticked in their list are added all at once with
    🛒 Add selected to order, one order each. A chemical switched to Out is added by itself, and taken
    off again if it is switched back before it is ordered.
  - The lab's **lab admins** (a role set in the suite) see the lab's orders, and no other lab's; the
    Orders tab shows how many wait. They mark each ordered, then received, or cancel it. When an
    order for a stock that had run out arrives, the stock is back in stock. The orders shown can be
    downloaded as a spreadsheet for a supplier's order form, with each primer's sequence in a column
    of its own. Stocks on the order list are marked 🛒 in their lists.
  - Everyone else sees their own requests and how far each has got, and can change or cancel one
    until it is ordered.
- **Shared with the other tools:**
  - storage, labels with QR codes (printed from the browser, or as files for DYMO Connect on LabTAG
    DYMO labels), photos and files;
  - links from the Lab Notebook (`@`), with the pages that mention each stock.
- **Who sees what:** a lab's stocks are shared within the lab and not seen by other labs.
  Administrators see all. Every change is logged.
- **Lab codes** are the same as the Seed Bank's when the lab has one there.

## Running it

It runs inside the [Gardiner Lab suite](https://github.com/Gardiner-Lab/gardiner-lab-suite) at
`/stocks/`, signed in through the suite. Don't expose it outside the proxy.

| Setting | Default | |
| --- | --- | --- |
| `STOCKS_DATABASE_PATH` | `/stocks/stocks.db` | its own data, files included |
| `MOCLO_DATABASE_PATH`, `SUITE_DATABASE_PATH` | `/moclo/moclo.db`, `/suite/suite.db` | accounts and labs (read only) |
| `EDITOR_DATABASE_PATH` | `/editor/plasmid_editor.db` | plasmids (read only) |
| `NOTEBOOK_DATABASE_PATH` | `/notebook/notebook.db` | notebook links (read only) |
| `SEEDS_DATABASE_PATH` | `/seeds/seeds.db` | the lab codes chosen in the Seed Bank (read only) |
| `SUITE_PUBLIC_URL` | (the page's own address) | where phones reach the suite, for label QR codes; the suite dashboard's Hosting tab sets it instead |
| `SOFOS_URL` | UU's SOFOS information portal | the hazardous substances register chemicals link to |
| `CHEMWATCH_URL` | `https://jr.chemwatch.net/chemwatch.web/` | Chemwatch, which chemicals link to |
| `ELAB_URL`, `ELAB_TOKEN` | (off) | copy every lab's glycerol stocks and seed lots to eLabJournal, for labs not connected on the page (below) |
| `ELAB_LABS` | every lab | the suite labs copied, comma-separated |
| `ELAB_KINDS` | `glycerol,seed` | what is copied |
| `ELAB_SAMPLE_TYPES` | Glycerol Stock, Plant Seed | other sample type names, e.g. `seed=Seeds` |
| `ELAB_INTERVAL` | `120` | seconds between checks for changes |
| `ELAB_HOSTS` | `elabjournal.com,elabnext.com` | the hosts (and their subdomains) a lab may connect to |

## Plant material

Tubes of plant material kept for later processing (leaf, flower, root, ...),
coded GL-M-0001, each linked from the notebook by its code like any stock.
*＋ Tube* adds one; *📦 Box of tubes* adds many at once: numbered (L2201-1 to
L2201-81, with a suffix and zero padding if wanted) or a pasted list (one a
line; a second column, after a tab, its description), the rest of the form
shared by all, and in a box with places in eLab, filling them in order from the
place given. They go to eLab's *Plant Material* type (a name, description, note
and place).

## Bringing over from eLab

*⇩ Bring over from eLab…* (the lab admin, once the lab is connected) lists eLab's
Plant Material or Plant Seed samples not yet linked to a record here, by owner
and where they are kept, and brings the chosen ones over: plant material as
tubes here, in their places; seed samples to the Seed Bank, one line per cross
or note with each sample a seed lot of it (made through the Seed Bank's own
API, as the person signed in). Each is linked to its sample in eLab, which keeps
its name; nothing is changed there until the record is changed here.

## Chair groups

Labs that work together (a chair group, a department) can see each other's
stocks. Chair groups are the suite's: an administrator makes them and puts labs
in them on the dashboard's Labs tab (/account/), and Lab Stocks reads them from
the suite's database. Each lab is in one at most; the lists say which.

- In a list, *Show the stocks of the other labs of …* adds theirs, each tagged
  with its lab; the choice is remembered in the browser.
- Another lab's stock opens read-only: it can be seen, labelled and searched for
  (notebook links too), but only its own lab changes, deletes, attaches files to
  or orders it. The Plasmid Editor binds only the lab's own primers.
- eLab stays per lab: each lab sends its own stocks with its own token; in a
  shared eLab group, a sample's owner says whose it is.

## eLabJournal

Lab Stocks copies a lab's **glycerol stocks**, and its **seed lots** from the Seed
Bank, to eLabJournal's inventory, one way: change them here (or in the Seed
Bank), and eLab follows. Primers, chemicals and antibodies are not copied.

**Connecting a lab.** Its lab admin clicks *Connect to eLabJournal…* above any
list, and is walked through it: open eLab, make a token there (Apps &
Connections > Manage Authentication, on the eLab Mobile App card), paste it, and
choose, for glycerol stocks and seed lots, which of the group's sample types
they go to (Glycerol Stock, Plant Seed) and the lab's **Permit** and
**Biosafety level**, from that type's own options. The token is tried before it
is kept, in Lab Stocks' database (so in its backups too), and never shown again.
Each lab connects with its own token. *eLab settings…* changes this later, or
stops it. Only eLab hosts are accepted (`ELAB_HOSTS`).

The eLab group is usually shared by a chair group, so **nothing is added to its
sample types**: no types are made, no fields added. Values go into the fields
the type has, and a value for a field with options is sent only when it is one
of them (as eLab spells it):

| Glycerol stock | → *Glycerol Stock* |
| --- | --- |
| code, plasmid, clone | the sample's name; the code is its alternative id |
| strain | *Name of host strain*, and *Host system* worked out from it (DH5α: E. coli, GV3101: Agrobacterium / Rhizobium, ...) |
| selection; plant and yeast markers | *Bacterial Markers*; *Plant Markers*, *Yeast Markers* |
| permit, biosafety level, host system (empty: the lab's, or from the strain) | *Permit*, *Biosafety level*, *Host system* |
| insert(s), gene IDs, donor organism(s), harmful gene product and remarks | the fields of those names |
| the plasmid linked in the Plasmid Editor | *Plasmid sequence*, *Molecular weight (in kb)* |
| storage location (eLab), and the place in a box | the sample is put there in eLab's storage |
| plasmid, clone, where kept, made on, notes | *Remarks* |

| Seed lot (Seed Bank) | → *Plant Seed* |
| --- | --- |
| code, line | the sample's name; the code is its alternative id |
| species, background, generation, harvest date | *Species*, *Genetic background*, *Generation*, *Harvest Date* |
| the plants it came from | *Mother plant*, *Father plant*, *Cross* |
| zygosity | *Zygosity* (homozygous, heterozygous, hemizygous) |
| the line transgenic, with plasmids, or a T-DNA or plasmid GMO type; wild type | *GMO* Yes; No (else Unknown) |
| the line's permit and biosafety level (empty: the lab's), GMO type, gene expression, selection marker, mutation information, construction method | the fields of those names |
| the line's stock center collection and number, accession, link | *Line*, *Stock center number*, *Stock center line*, *Accession*, *Web link stock center* |
| who entered the lot in the Seed Bank | *Harvested by* |
| line, amount, where kept, germination, source, notes | *Description* |

- **Storage location.** A glycerol stock's form has *Storage location (eLab)*: every
  compartment of the group's storage units (freezers, towers, shelves, boxes;
  not its equipment), found by typing, and for a box with places, the place
  (its number, as eLab shows it; B3 too in a box with lettered rows). *New location under the one
  chosen* adds a compartment in eLab, of a kind that unit has at that level (a
  shelf under a tower, a box under a shelf), and chooses it. eLab's storage is
  read when the form opens and kept for ten minutes (↻ reads it again). Anyone
  in the lab may add one. The free-text *Kept in* stays as well.
- Used up, discarded or deleted: **archived** in eLab. Brought back: a new sample.
- A record's page links to its sample in eLab (*In eLabJournal: sample … ↗*,
  opening it in eLab's inventory) and says how it stands: sent, waiting, not
  sent and why, or archived.
- Archived in eLab (by someone there): left so: no longer sent, never made again;
  the list pages count them. *Send to eLab again* on its page sends it to the
  same sample if it was restored in eLab meanwhile (eLab's Restore), else as a
  new one. A sample this account may not change (someone
  else's, brought over from eLab) is listed as failed, naming its owner.
- Anything changed in eLab is overwritten by the next change here.
- Glycerol stocks are sent straight after a change; seed lots, changed in the
  Seed Bank, at the next round (every `ELAB_INTERVAL` seconds, 2 minutes).
- **Nothing is made twice.** A record is found again in eLab by its code (the
  sample's barcode) or, sent without one, by its name, before anything is made;
  a code already a live sample's barcode is listed as failed, not made again;
  a seed lot brought over from eLab (its source "eLab sLAB…") is only ever
  linked to that sample, never sent as new; plant material is made and linked
  with the sync paused; an eLab sample is linked to one record at most; and the
  import leaves out what was brought over already. Connect each lab from one
  installation only: a test copy sending the same lab would find and change
  the same samples.
- What was sent is kept in `elab_links`; what eLab refused is tried again after
  ten minutes, or at once when it changes. The list pages say how many are sent,
  waiting and failed; the lab admin can send at once.

Signing in to UU's eLab goes through the university, so a token cannot be had
from a username and password. Without a lab's own connection, the `ELAB_`
settings above connect every lab (or those in `ELAB_LABS`), without a permit or
biosafety level.

## Licence

GNU General Public License v3.0; see [LICENSE](LICENSE) and [NOTICE](NOTICE).
