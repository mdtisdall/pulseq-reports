// The gamma control of a card that has no other script (markup.gamma_select_html): a click
// on a button shows the block of that gamma (`data-gamma-entry`) and hides the others.
// A card with its own script calls `PulseqReport.gammaSelect` from that script.
PulseqReport.registerCard("gamma-select", section => PulseqReport.gammaSelect(section));
