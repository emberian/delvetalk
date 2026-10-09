# Structured documents

`Document.obend` is a pure, recursively typed presentation value shared by authored
encounters, templates and interpretation prompts. It imports the actual Preparation
and Encounter prelude modules. See the [conversation contract](../../../protocols/conversation/README.md)
for the capture, attribution, continuation and receiving boundaries.

`plain` is an authored text projection. Keep the structured original: concatenated
text cannot manufacture an offer, reference, field or instruction boundary.
Templates live in `templates/`; renderers may adapt layout but must resolve actions
through the same retained invitation and display unbound captures inertly.
