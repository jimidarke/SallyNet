sub init()
    m.status = m.top.findNode("status")
end sub

sub onStatus()
    if m.status <> invalid then m.status.text = m.top.status
end sub
