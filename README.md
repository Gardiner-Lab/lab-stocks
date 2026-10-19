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
  - storage, labels with QR codes, photos and files;
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
| `SUITE_PUBLIC_URL` | (the page's own address) | where phones reach the suite, for label QR codes |
| `SOFOS_URL` | UU's SOFOS information portal | the hazardous substances register chemicals link to |
| `CHEMWATCH_URL` | `https://jr.chemwatch.net/chemwatch.web/` | Chemwatch, which chemicals link to |

## Licence

GNU General Public License v3.0; see [LICENSE](LICENSE) and [NOTICE](NOTICE).
