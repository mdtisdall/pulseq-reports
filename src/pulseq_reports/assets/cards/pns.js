// PNS prediction card (cards/pns.py): the button that shows the peak in the sequence
// diagram. The card's data is `{format: 1, goto}`, and `goto` is the payload of the
// message that the button sends: `{t0S, t1S, anchorS}`, the TR that holds the peak and
// the peak time, or `{block}`, the block that holds it when the sequence has no `TR`
// definition (`pns.peak_tr_window`). The button is shown only while a card subscribes
// to `goto` (decision 22 of docs/plans/public-api.md), so on a page with no diagram it
// stays hidden. A card that has no prediction has no data and no script.
PulseqReport.registerCard("pns", (section, data) => {
  const id = section.id;
  if (data.format !== 1) {
    throw new Error(`PNS card: unsupported data format ${data.format} (only format 1 is known)`);
  }
  const button = document.getElementById(`${id}-goto`);
  PulseqReport.requestButton(button, "goto");
  button.addEventListener("click", () => {
    PulseqReport.publish("goto", {source: id, ...data.goto});
  });
});
