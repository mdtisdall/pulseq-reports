// The "Show" buttons of a card (markup.show_button_html): each button has the play index of
// one block in `data-block`, and a click sends the `goto` message `{source, block}`, which
// the sequence diagram acts on. The buttons are shown only while a card subscribes to
// `goto` (decision 22 of docs/plans/public-api.md), so on a page with no diagram they stay
// hidden. A card with these buttons registers no other script.
PulseqReport.registerCard("show-buttons", section => {
  const id = section.id;
  for (const button of section.querySelectorAll("button[data-block]")) {
    PulseqReport.requestButton(button, "goto");
    button.addEventListener("click", () => {
      PulseqReport.publish("goto", {source: id, block: Number(button.dataset.block)});
    });
  }
});
