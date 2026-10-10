# Layout

The perch checkout is home. A project is one GitLab project, one Budgie
project and one timesheet charge code, and everything about it sits under
`projects/NAME/` (gitignored, like `apps/`).

```
perch/                     the clone you ran make install in
  config.yaml              optional, gitignored: lead: Your Name, and alerts:
  apps/budgie/             clones, put there by make install
  apps/remote-gitboard/
  projects/apollo/
    perch.yaml             gitlab_project: group/apollo, people:, estimates:
    board/                 apollo.yaml (the pulled board), its .base, snapshots, stats, dump.json
    budget/                the Budgie project: budgie.yaml, people.csv, plan.csv, weekly.csv
    reports/               gitboard's digests
    listen/                meeting transcripts, one DATE.txt each
    history.jsonl, weekly/, watch/
```

perch hands gitboard explicit paths (`--out`, `--db`, `--log`, `--spec`,
`--boards-dir`), so it writes nothing inside gitboard's checkout. Pick a
project with `-p NAME`.
