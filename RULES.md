# RULES.md

**This file governs process. `CLAUDE.md` governs the project. Where the two
disagree, RULES.md wins.**

RULES.md says how work is done: how a task is split into phases, what evidence
is required, where the record is kept, what may not be changed without asking.
CLAUDE.md says what the tool is and what it guarantees. A statement about *how
to work* belongs here; a statement about *what the code does* belongs there.

These rules exist because this project's failure mode is not broken code. It is
a plausible, confident, wrong statement — a number transcribed from the wrong
method, a caveat softened into a reassurance, a constant quietly retuned until
the output looked right. Every rule below is aimed at that.

---

## 1. The two-phase protocol

Work is split into two phases. They are separate turns, separated by an explicit
human approval. They are never merged.

### PHASE A is verification only

Read files. List directories. Run read-only commands. Inspect data.

**Create, edit, move and delete nothing** except that phase's own file under
`prompt_outputs/`. Install nothing. Do not create a virtual environment, add a
dependency, or upgrade a package.

Take every assumption in the request and check it against the actual code and
the actual data. Report each one as **CONFIRMED**, **CONTRADICTED** or
**UNKNOWN**, with concrete evidence: a count, a printed line of output, a quoted
line of source. An assumption reported without evidence has not been checked.

State explicitly what could **not** be checked, and why. An unstated gap reads
as a clean bill of health, and that is how a gap becomes a false assurance.

Then list PROPOSED DEVIATIONS: anything you believe should be done that the
request did not ask for. List them; do not do them.

Then **stop and wait**.

### PHASE B is implementation only

Phase B begins only after an explicit **"PROCEED"**. Not after a question that
sounds encouraging, not after silence, not after "looks good" on something else.

**Before implementing, re-check that Phase A's confirmed assumptions still
hold.** Approval may arrive days later. Evidence has a shelf life: files change,
the tree moves, a value that was true when it was measured may not be true when
it is acted on. If anything has changed, stop and report rather than proceeding
on stale verification.

### NO SILENT CHANGES

Anything not written in the request is not to be done. This includes:

- renaming anything
- extracting a helper, or inlining one
- adding a package, a file, or a directory
- restructuring, reordering or reformatting code you were not asked to touch
- fixing an unrelated bug you noticed
- any "improvement"

Stop, list it under PROPOSED DEVIATIONS, and wait.

**This applies with full force when the change seems obviously beneficial.**
"Obviously beneficial" is precisely the judgement that is not yours to make
alone — it is the judgement that feels most safe to act on and is least often
checked. The cost of asking is one turn. The cost of an unrequested change is
that nobody knows it happened.

If an assumption turns out to be false mid-implementation, **do not work around
it**. Report and wait. A workaround built on a false premise is worse than a
halt, because the halt is visible.

---

## 2. Saving prompt outputs

Every Phase A and every Phase B produces a file under `prompt_outputs/`, in
markdown, **in full** — the report itself, not a summary of it.

### Naming

```
NNN-short-slug-phaseA.md
NNN-short-slug-phaseB.md
```

`NNN` is a zero-padded sequence that **never resets**. Both phases of one task
share a number: `002-zsmooth-governance-phaseA.md` and
`002-zsmooth-governance-phaseB.md` are the two halves of task 002.

A read-only task with no Phase B uses:

```
NNN-short-slug-audit.md
```

### The file is written BEFORE reporting in chat

Not after. The on-disk copy must never be the summarised one. Write the record,
then derive the chat report from it.

### The directory is TRACKED in git

`prompt_outputs/` is committed. It is a decision record. The reasoning behind a
change is worth as much as the change itself, and once the conversation that
produced it has ended, that reasoning exists nowhere else.

### APPEND-ONLY

**Never edit and never delete an existing file in `prompt_outputs/`.**

A re-run of a task gets a **new number**, and states at the top which number it
supersedes and why. The superseded file stays exactly as it was. A record that
can be revised is not a record.

Append-only binds a record **once its phase has reported**. Until then the file
is still being drafted and may be revised freely — the constraint is on
rewriting history, not on finishing a sentence.

### The file is a SUPERSET of the chat report, never a subset

Beyond everything in the chat report, it must carry:

- **any deviation from the prompt**, and the reasoning for it
- **any self-correction**: what was said first, what the correct statement is,
  and how that was established
- **anything measured or validated during the phase, with the numbers** —
  including measurements that did not make it into the final answer

### INDEX.md

`prompt_outputs/INDEX.md` gets **one appended line per entry**: number, slug,
which phases are present, the date, and one sentence on what the task did or
found.

INDEX.md is infrastructure. It carries no number of its own and is the one file
in `prompt_outputs/` that is appended to rather than added.

---

## 3. When a phase goes wrong

If Phase B fails partway — a command errors, a file is not what Phase A found it
to be, a step produces something unexpected — **STOP**.

**Leave the working tree exactly as it is.** The half-finished state is
evidence. It shows how far the work got and where it broke, and that
information is destroyed by tidying up.

Write the `prompt_outputs/` file anyway, containing:

- what was completed
- what failed
- the **verbatim** error text, not a paraphrase of it

Report in chat: what was done, what failed, the current state of the tree, and
what you propose to do about it. Then **wait**.

**Reverting is a decision, not a cleanup.** Ask before undoing anything.

---

## 4. Evidence standards

**Prove it, don't assert it.**

### Scope every claim precisely

"The only instance in this function", "the only instance in this module" and
"the only instance in the repository" are three different claims requiring three
different checks. Say which one you actually made. A claim whose scope is
unstated will be read at the widest scope, which is usually the one you did not
check.

### Say UNCERTAIN rather than guessing

A false "this is unused" is worse than an honest "I did not check whether this
is used". The honest gap gets checked by someone. The false claim gets acted on.

### Distinguish what you verified from what you were told

If the request asserted it and you confirmed it, say both. If the request
asserted it and you did not confirm it, attribute it to the request and mark it
unverified. Never launder a prompt's claim into a finding.

### Quote the actual current code

For anything about to be modified, quote the code as it is right now — not a
description of it, not a paraphrase, and not what you remember it saying from
earlier in the conversation.

### Never regenerate a baseline to make a check pass

Never regenerate a baseline, a reference output, a fixture or a stored expected
value in order to make a failing check pass. **The failure is the finding.**
Regenerating it destroys the only evidence that something changed.

The same prohibition covers parameter choice: no value may be selected by
checking which one reproduces an expected result.

---

## 5. Report structure

**FIRST LINE is a status line**: phase, task slug, HEAD hash, and the number of
items needing a decision.

```
PHASE B - zsmooth-governance - 934f617 - 0 decisions needed
```

If that number is not zero, **those items come first and nothing precedes
them** — no preamble, no summary, no "here's what I did".

Then, in this order:

1. Blockers and questions needing a decision
2. PROPOSED DEVIATIONS
3. What changed: files, and `git diff --stat`
4. Demonstrations
5. **Matters next.**

**LAST LINE is exactly:**

```
--- END OF REPORT ---
```

so that truncation in transit is visible.

### Report conventions

- **No box-drawing characters.**
- **State each fact once.** A fact repeated in three sections reads as three
  facts.
- **Reference code by function or heading name, never by line number.** Line
  numbers go stale the moment anything above them shifts, and a stale reference
  is worse than no reference, because it points confidently at the wrong thing.
- **Do not paste full diffs into chat.** See section 6.

---

## 6. The diff artifact

Every Phase B additionally writes the complete working-tree diff to:

```
prompt_outputs/NNN-short-slug-diff.txt
```

**Before generating it, run `git add -N` on any newly created files**, or they
will not appear in the diff at all — git does not diff what it has never heard
of, and a new file is exactly the change most worth seeing.

The chat report carries `git status --short` and `git diff --stat`, plus a prose
account of what changed and why. The full diff lives in the file.

Both are required. The summary states intent; the diff states fact. **A
disagreement between them is itself a finding** — it means the change made is
not the change described.

---

## 7. Committing and pushing

**PHASE B ENDS BEFORE THE COMMIT.**

Do not commit as part of Phase B. Do **not** include a proposed commit message
in the Phase B report: a message drafted before the report is approved describes
a change that may still be rejected, and it quietly presumes the answer.

After the report is approved, propose a message. Format is **50/72**:

- subject 50 characters or fewer, imperative mood, no trailing full stop
- blank line
- body wrapped at 72 columns, explaining **WHY**, not what the diff already
  shows

The body ends with one `Record:` line per `prompt_outputs/` entry the commit
covers:

```
Record: prompt_outputs/002-zsmooth-governance-phaseB.md
```

Once the message is approved, **commit AND push**, and report both in one turn:
the commit hash, the push output, and `git status`.

**If any gate is not explicitly answered, wait. Silence is not approval.**

---

## 8. Running things

**There is currently NO virtual environment and NO tests.** The tool runs on the
machine-wide interpreter.

The current results were produced under this environment. These values are taken
from the Phase A audit `prompt_outputs/001-zsmooth-recon-audit.md`; they are
recorded, not re-measured:

```
interpreter : CPython 3.14.2
              C:\Users\berke.santos\AppData\Local\Programs\Python\Python314\python.exe
numpy       : 2.4.1
pandas      : 3.0.0
matplotlib  : 3.10.8   (optional; needed only for --plot)
pip         : 26.2.1
```

`requirements.txt` declares lower bounds only (`numpy>=1.24`, `pandas>=2.0`).
The installed `pandas 3.0.0` is a major version beyond anything that file
anticipated. It works today; nothing pins it.

**A pinned environment is intended but has not been created.** A future session
must not assume one exists, must not assume `.venv/` is present, and must not
silently create one — creating it is a change, and changes are proposed, not
made. `.gitignore` lists `.venv/`, `venv/` and `env/`, but none of those
directories exists.

**There are no tests.** There is no `tests/` directory, no test runner
configuration and no CI. `.gitignore` carries a `!tests/fixtures/*.csv` negation
for a tree that does not exist. Do not describe what tests could be added unless
asked; do not add them unasked.

---

## 9. What is irreversible

Almost everything in this project can be regenerated. Two things cannot.

### The input data under `data/`

It is **gitignored, so git will NOT protect it.** There is no commit to restore
it from and no branch it survives on. Nothing in the tool writes there, and
nothing should.

This is the only thing in the project that cannot be regenerated from anything
else. Treat any operation that touches `data/` as irreversible and confirm it
first.

### `prompt_outputs/`

The reasoning it holds existed only in conversations that no longer exist. A
deleted entry cannot be rebuilt from the code, from the git history, or by
asking again — the context that produced it is gone. This is why section 2 makes
the directory append-only.

### Everything under `out/` is regenerable

`out/` is build output. The tool rewrites it on every run. It carries no
information that is not reproducible by re-running the tool with the arguments
recorded in the report it contains.
