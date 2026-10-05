// Gradient limits card (cards/gradient_limits.py): the "Show" button of each peak and max
// slew. A button holds the view and the anchor of its `goto` message in `data-t0`, `data-t1`
// and `data-anchor` (seconds): the block where the value is reached, with half the block's
// duration on each side, and the time of the value. The buttons are shown only while a card
// subscribes to `goto` (decision 22 of docs/plans/public-api.md), so on a page with no
// diagram they stay hidden. The card has no data. The card also runs its gamma control, when
// it has one (more than one |gamma| among the targets): it shows the table of the pressed entry.
PulseqReport.registerCard("gradient-limits", section => {
  const id = section.id;
  PulseqReport.gammaSelect(section);
  for (const button of section.querySelectorAll("button[data-anchor]")) {
    PulseqReport.requestButton(button, "goto");
    button.addEventListener("click", () => {
      PulseqReport.publish("goto", {
        source: id,
        t0S: Number(button.dataset.t0),
        t1S: Number(button.dataset.t1),
        anchorS: Number(button.dataset.anchor),
      });
    });
  }
});
