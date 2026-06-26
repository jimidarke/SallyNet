sub init()
    m.qr = m.top.findNode("qr")
    loadQr()
end sub

' Cache-bust so the Poster re-reads if the api base changed (a no-op string is ignored).
sub loadQr()
    m.qr.uri = snQrUrl() + "?t=" + snNowSeconds().toStr()
end sub

sub onRefresh()
    loadQr()
end sub

function onKeyEvent(key as string, press as boolean) as boolean
    if not press then return false
    if key = "back" then
        m.top.requestBack = true
        return true
    end if
    return false
end function
