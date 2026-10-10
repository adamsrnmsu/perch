---
layout: landing
---

# perch

```{raw} html
<div class="pl">
<section class="pl-hero">
<img class="pl-logo pl-logo-light" src="_static/logo-light.png" alt="perch">
<img class="pl-logo pl-logo-dark" src="_static/logo-dark.png" alt="">
<span class="pl-badge">for one lead &middot; nothing is ever sent</span>
<h1>The work, joined to the money.</h1>
<p>perch joins gitboard's board to Budgie's budget and answers one question: what does the open board cost, against the hours and the budget that are left?</p>
<div class="pl-btns"><a class="pl-btn primary" href="install.html">make install</a><a class="pl-btn" href="guide.html">perch monday</a></div>
</section>
<h2>What it does</h2>
<div class="pl-grid"><div class="pl-card"><code>perch monday</code><h3>Monday run</h3><p>Fetch, board, weekly, digest and emails for every project in one command. Resume at any step after a failure.</p></div><div class="pl-card"><code>perch board</code><h3>Budget join</h3><p>What does the open board cost against the hours and budget left? Budgie's engine, gitboard's issues.</p></div><div class="pl-card"><code>perch accuracy</code><h3>Accuracy</h3><p>Estimate misses by label (modelled) and by person (measured). Never a ranking.</p></div><div class="pl-card"><code>perch walk</code><h3>Walk</h3><p>Claude reads the brief, walks money, board and watch, and stages your calls as board edits.</p></div><div class="pl-card"><code>perch listen</code><h3>Listen</h3><p>Drop in a meeting transcript. Your lines become staged board edits, in the issue template.</p></div><div class="pl-card"><code>perch gb sync</code><h3>gb sync</h3><p>Plan, confirm, push, snapshot. Close issues and drop columns from the file; the pull comes first if needed.</p></div></div>
<h2>Up in 60 seconds</h2>
<ol class="pl-steps"><li><code>git clone https://github.com/adamsrnmsu/perch.git &amp;&amp; cd perch</code></li><li><code>make install</code></li><li><code>perch init NAME</code></li><li><code>perch monday -p NAME</code></li></ol>
<h2>From the meeting to the board</h2>
<div class="pl-flow"><svg viewBox="0 0 800 170" role="img" aria-label="A meeting transcript becomes staged edits in the board file, which gitboard pushes to GitLab"><rect class="box" x="10" y="40" width="200" height="90" rx="14"/><text class="t" x="110" y="80" text-anchor="middle">Transcript</text><text class="s" x="110" y="106" text-anchor="middle">meeting.vtt</text><path class="a" d="M210 85 H270"/><path class="ah" d="M270 85 l-9 -5 v10 z"/><text class="s" x="240" y="70" text-anchor="middle">listen</text><rect class="box hot" x="270" y="40" width="200" height="90" rx="14"/><text class="t" x="370" y="80" text-anchor="middle">Board file</text><text class="s" x="370" y="106" text-anchor="middle">apollo.yaml</text><path class="a" d="M470 85 H530"/><path class="ah" d="M530 85 l-9 -5 v10 z"/><text class="s" x="500" y="70" text-anchor="middle">gb sync</text><rect class="box" x="530" y="40" width="200" height="90" rx="14"/><text class="t" x="630" y="80" text-anchor="middle">GitLab</text><text class="s" x="630" y="106" text-anchor="middle">issues and boards</text><text class="s" x="370" y="158" text-anchor="middle">you read the plan before anything is sent</text></svg></div>
<p class="pl-foot">perch never calls GitLab itself, never redoes budget math and never ranks people.</p>
</div>
```

```{toctree}
:hidden:

install
layout
gitboard
listen
issue-template
guide
reference
```
