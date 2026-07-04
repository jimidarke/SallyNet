sub init()
    m.poster = m.top.findNode("poster")
    m.bg = m.top.findNode("bg")
    m.fadeIn = m.top.findNode("fadeIn")
    m.cap = m.top.findNode("cap")
    m.stripeRed = m.top.findNode("stripeRed")
    m.stripeOrange = m.top.findNode("stripeOrange")
    m.kidBadgeBg = m.top.findNode("kidBadgeBg")
    m.kidBadgeLabel = m.top.findNode("kidBadgeLabel")

    m.poster.observeField("loadStatus", "onPosterLoad")
    ' Zoom about the card's centre so the focus scale grows evenly (not off a corner).
    m.top.scaleRotateCenter = [150, 112]
end sub

sub onContent()
    c = m.top.itemContent
    if c = invalid then return
    m.poster.opacity = 0.0   ' fade the new image in once it's ready (onPosterLoad)
    if c.hdPosterUrl <> invalid and c.hdPosterUrl <> "" then
        m.poster.uri = c.hdPosterUrl
    else
        m.poster.uri = "pkg:/images/transparent.png"
    end if
    line = ""
    if c.title <> invalid then line = c.title
    if c.shortDescriptionLine1 <> invalid and c.shortDescriptionLine1 <> "" then
        if line <> "" then line = line + "  ·  "
        line = line + c.shortDescriptionLine1
    end if
    m.cap.text = line
    ' kidSafe is omitted (invalid), not false, until overrides/TMDB data exists — the badge
    ' only ever shows once that data is genuinely known, never on a guess.
    showKidBadge = (c.kidSafe = true)
    m.kidBadgeBg.visible = showKidBadge
    m.kidBadgeLabel.visible = showKidBadge
end sub

sub onPosterLoad()
    ' Crossfade the poster over the placeholder once it decodes; a failed/empty load
    ' leaves the muted placeholder showing (never a blank card).
    if m.poster.loadStatus = "ready" then m.fadeIn.control = "start"
end sub

sub onFocusChange()
    fp = m.top.focusPercent
    focused = (fp > 0.5)
    m.stripeRed.visible = focused
    m.stripeOrange.visible = focused
    if focused then
        m.cap.color = SN_INK()
    else
        m.cap.color = SN_MUTED()
    end if
    ' Netflix-style poster zoom, tracking focusPercent smoothly (1.0 -> ~1.08).
    s = 1.0 + 0.08 * fp
    m.top.scale = [s, s]
end sub
