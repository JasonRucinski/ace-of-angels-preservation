# Research records

How the client, the protocol and the maps were worked out, kept as dated
records. A guide says what is true now and is kept current; a record says
what was found on a day and how it was checked, and stays as it was written.

- **Dated, and not rewritten.** Every entry and section carries its date.
  When later work corrects one, the correction is a new dated section or an
  "Update" line that links forward ([findings 9.37](findings.md#937-a-dormant-chase-camera-revived-on-f2-23-october-2026) is
  corrected by [9.47](findings.md#947-an-orbit-camera-on-f4-f2-was-never-unbound-2627-october-2026)); the older text stays.
- **Verified or not, every time.** Each record says how a result was
  checked: a live client, original code run in emulation, a synthetic test
  client, or not at all. [findings.md](findings.md) labels its static results
  CONFIRMED, INFERENCE or HYPOTHESIS. "The user" in these records is the
  project owner, who ran the live tests.
- **Current state is elsewhere.** What works today, and what is untested, is
  in [STATUS.md](../STATUS.md), which links back to the record behind each row.
- **Adding to them.** New development work gets a dated entry at the top of
  [log.md](log.md). A client or protocol investigation gets the next numbered
  section of [findings.md](findings.md), with its `<a id="s9-N">` anchor, and
  the log entry links to it. Machine-readable results go in `evidence/`
  (indexed in `evidence/INDEX.tsv`).

The list of records, with what each covers, is in the
[docs index](../README.md).
