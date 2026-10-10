# Listen to a meeting

```bash
perch listen MEETING.vtt -p apollo
```

takes a WebVTT transcript (Teams, Zoom, Meet) and keeps only your lines. Set
`lead: Your Name` in `config.yaml`, spelled as the transcript spells it (`Ryan`
does not match `Ryan Adams`). The lines are saved to
`projects/apollo/listen/DATE.txt` (a second run the same day writes
`DATE-2.txt`; nothing is overwritten), then `/listen` opens in Claude.

`/listen` turns your lines into staged edits in the pulled board file: moves,
epics, milestones, new tasks in the {doc}`issue template <issue-template>`,
`closed: true`, a dropped column. Anything it cannot map to a board change is
listed, not guessed. It never touches GitLab and ends with
`perch gb plan -p apollo`, an offline table against the `.base`.

Read the plan, then apply where GitLab is reachable:
`perch gb sync -p apollo`. Needs a pulled board (`perch gb pull -p apollo`).
Stops, before Claude opens, when no lead is set, no line matches, or the file
is unreadable.
