"""A test plugin: a card that a package can add through the entry-point group
`pulseq_reports.cards`. It is not a test file, so pytest does not collect it.

`SPEC` is the plugin, and `BROKEN` is a spec whose card raises (an error card).
`make_spec` makes other specs with the same script and CSS, for the tests that need more
than one spec. The card reads the options that its spec declares and shows their values in
`data-` attributes of its body.
"""

from pulseq_reports import options
from pulseq_reports.page import Card
from pulseq_reports.registry import CardSpec, Option

SCRIPT = (
    'PulseqReport.registerCard("plugin-demo", (section) => { section.dataset.started = "yes"; });'
)
CSS = ".plugin-demo { font-style: italic; }"


def make_spec(
    name: str, order: float, read: tuple[Option, ...] = (options.max_rows,), **spec_fields
) -> CardSpec:
    """A spec of the plugin's card, with the card id `name`. It declares, and reads, the
    options `read`. `spec_fields` are other fields of the `CardSpec` (for example `when`)."""

    def build(ctx) -> Card:
        attributes = "".join(
            f' data-{option.name.replace("_", "-")}="{ctx.option(option)}"' for option in read
        )
        return Card(
            id=name,
            title="Plugin demo",
            body_html=f'<p class="plugin-demo"{attributes}>A card of a plugin.</p>',
            script="plugin-demo",
            scripts=(SCRIPT,),
            css=(CSS,),
        )

    return CardSpec(name, order, build, read, **spec_fields)


def _broken_build(ctx) -> Card:
    raise NotImplementedError("this card refuses the sequence")


SPEC = make_spec("plugin-demo", 55)
BROKEN = CardSpec("plugin-broken", 56, _broken_build)
