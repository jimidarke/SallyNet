sub init()
    m.poster = m.top.findNode("poster")
    m.cap = m.top.findNode("cap")
    m.stripeRed = m.top.findNode("stripeRed")
    m.stripeOrange = m.top.findNode("stripeOrange")
    m.kidBadgeBg = m.top.findNode("kidBadgeBg")
    m.kidBadgeLabel = m.top.findNode("kidBadgeLabel")
end sub

sub onContent()
    c = m.top.itemContent
    if c = invalid then return
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
    ' kidSafe is omitted (invalid), not false, until overrides/TMDB data exists (Phase 4) —
    ' badge only ever shows once that data is genuinely known, never on a guess.
    showKidBadge = (c.kidSafe = true)
    m.kidBadgeBg.visible = showKidBadge
    m.kidBadgeLabel.visible = showKidBadge
end sub

sub onFocusChange()
    focused = (m.top.focusPercent > 0.5)
    m.stripeRed.visible = focused
    m.stripeOrange.visible = focused
    if focused then
        m.cap.color = SN_INK()
    else
        m.cap.color = SN_MUTED()
    end if
end sub
