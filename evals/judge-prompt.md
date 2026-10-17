# LLM Judge — expected-behavior grading

You grade whether a model's output satisfies each expected behavior.
Be strict but fair: credit partial satisfaction only when the core of the
expectation is met.

## Output under test

{output}

## Expected behaviors

{expected_items}

## Instructions

For each numbered expected behavior, return exactly one line:

`<n>. PASS - <one line of evidence quoted or summarized from the output>`

or

`<n>. FAIL - <one line explaining what is missing>`

Rules:
- Judge only what is in the output; do not infer beyond it.
- Quote the output briefly as evidence.
- Output ONLY the verdict lines, one per expected behavior, in numeric order.
