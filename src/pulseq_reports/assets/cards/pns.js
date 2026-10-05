// PNS prediction card (cards/pns.py): the buttons that show the peak of a target in the
// sequence diagram. The card's data is `{format: 2, goto}`, and `goto` is a list with one
// entry for each target, in the order of the targets. An entry is the payload of the
// message that the button of that target sends: `{t0S, t1S, anchorS}`, the TR that holds
// the peak and the peak time, or `{block}`, the block that holds it when the sequence has
// no `TR` definition (`pns.peak_tr_window`); it is null for a target that has no button.
// The button of target `k` has the id `{card_id}-goto-{k}`. A button is shown only while a
// card subscribes to `goto` (decision 22 of docs/plans/public-api.md), so on a page with no
// diagram it stays hidden. A card with no button has no data and no script.
PulseqReport.registerCard("pns", (section, data) => {
  const id = section.id;
  if (data.format !== 2) {
    throw new Error(`PNS card: unsupported data format ${data.format} (only format 2 is known)`);
  }
  data.goto.forEach((goto, k) => {
    if (goto === null) return;
    const button = document.getElementById(`${id}-goto-${k}`);
    PulseqReport.requestButton(button, "goto");
    button.addEventListener("click", () => {
      PulseqReport.publish("goto", {source: id, ...goto});
    });
  });
});
