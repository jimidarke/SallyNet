sub init()
    m.card = m.top.findNode("card")
    m.label = m.top.findNode("label")
    m.stripeRed = m.top.findNode("stripeRed")
    m.stripeOrange = m.top.findNode("stripeOrange")
    onRender()
end sub

sub onRender()
    m.label.text = m.top.tileLabel

    if m.top.enabled = false then
        m.card.color = SN_ALMOND()
        m.card.opacity = 0.55
        m.label.color = SN_MUTED()
        m.stripeRed.visible = false
        m.stripeOrange.visible = false
        return
    end if

    m.card.opacity = 1.0
    m.label.color = SN_INK()
    if m.top.focused then
        m.card.color = SN_CREAM()
        m.stripeRed.visible = true
        m.stripeOrange.visible = true
    else
        m.card.color = SN_ALMOND()
        m.stripeRed.visible = false
        m.stripeOrange.visible = false
    end if
end sub
