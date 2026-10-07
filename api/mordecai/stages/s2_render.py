"""S2: hand the chosen readings to a provider and return its rendering. The
provider is injected; this stage does not hold keys and does not log them."""
from __future__ import annotations

from .. import providers
from .types import Analysis, Rendered, Resolution


def render(a: Analysis, r: Resolution, target: str, provider, key: str | None) -> Rendered:
    chosen: list[providers.Chosen | None] = []
    for i, (tok, cands) in enumerate(zip(a.tokens, a.lattice)):
        c = r.choice[i]
        if c is None:
            chosen.append(None)
            continue
        rd = cands[c]
        chosen.append(providers.Chosen(i, tok, rd.prefix, rd.reading, rd.gloss(target)))
    req = providers.RenderRequest(a.source, a.src_lang, target, a.tokens, chosen)
    return Rendered(provider.render(req, key), provider.name, provider.notice)
