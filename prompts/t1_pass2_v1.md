# T1 pass 2: the notions of a chapter

A student is about to study a chapter of a course in a study app. Cut the chapter into
notions. The student validates the notions; the questions on each notion are written
afterwards, one notion at a time.

## Input

The JSON object between `<input>` and `</input>` gives:

- `subject`: the name of the subject;
- `chapter`: its number, its title and the objectives it serves;
- `files`: the files of the chapter. Each has its `id`, `name` and `kind`, the range of
  pages of the chapter from `first_page` to `last_page`, and the `text` of each page. A
  page mostly in images also has a `description` of what it shows. For a Markdown file,
  a page is a section.

## Notions

- A notion is one idea, read in 10 minutes at most: 6 pages at most, often fewer.
  Follow the sections of the text, in its order.
- `title` and `summary` (one line) in French.
- `file`, `first_page` and `last_page`: a single range of pages of one file of the
  chapter.
- Pages that teach nothing, such as references or lists of exercises, may stay out of
  the notions.
- `boundary_alert`: in French, if the chapter seems to start or end at the wrong place,
  for example when its last pages belong to the next topic; otherwise null.
