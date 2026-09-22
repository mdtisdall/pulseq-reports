// Runs last on the page. Starts each card: for each <section data-card-script="name">,
// calls the init function that the card script registered under that name with the
// section and the card's JSON data (or null). A card's init may return a promise (for
// example, to decompress its data); it is not awaited here, so it does not hold up the
// other cards, but a rejection shows the same failure note as a thrown error.
(() => {
  for (const section of document.querySelectorAll("section[data-card-script]")) {
    const name = section.dataset.cardScript;
    const init = PulseqReport.cards.get(name);
    // One card that fails does not stop the others. The card shows that it failed.
    const fail = error => {
      console.error(`card "${section.id}":`, error);
      const note = document.createElement("p");
      note.className = "status bad";
      note.textContent = `This card could not be drawn: ${error.message}`;
      section.appendChild(note);
    };
    try {
      if (init === undefined) throw new Error(`no card script is registered as "${name}"`);
      const dataElement = document.getElementById(`${section.id}-data`);
      const data = dataElement === null ? null : JSON.parse(dataElement.textContent);
      const result = init(section, data);
      if (result && typeof result.then === "function") result.catch(fail);
    } catch (error) {
      fail(error);
    }
  }

  // A chart focused by a click or tap shows no focus outline (Safari draws one on a click).
  // A chart focused with the keyboard keeps the outline.
  for (const svg of document.querySelectorAll(".chart svg[tabindex]")) {
    svg.addEventListener("pointerdown", () => svg.setAttribute("data-pointer-focus", ""));
    svg.addEventListener("blur", () => svg.removeAttribute("data-pointer-focus"));
  }
})();
