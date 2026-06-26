sub init()
    m.speed = m.top.findNode("speed")
    m.clock = m.top.findNode("clock")
    m.r1 = m.top.findNode("r1")
    m.r2 = m.top.findNode("r2")
    m.r3 = m.top.findNode("r3")
    m.r4 = m.top.findNode("r4")
    m.footer = m.top.findNode("footer")
end sub

sub onState()
    s = m.top.state
    if s = invalid then return

    gps = s.gps
    if gps <> invalid then
        m.speed.text = snFmt1(gps.speed_kmh)
        hd = "--"
        if gps.heading <> invalid then hd = snFmtInt(gps.heading) + " deg"
        m.r1.text = "Heading   " + hd
        m.r2.text = "Altitude  " + snFmtInt(gps.alt_m) + " m"
        hasFix = (gps.fix = true)
        m.r4.text = "GPS   " + iif(hasFix, "fix - " + snFmtInt(gps.sats) + " sats", "no fix")
    end if

    drive = s.drive
    if drive <> invalid then
        if drive.km_from_home <> invalid then m.r3.text = "From home " + snFmt1(drive.km_from_home) + " km"
    end if

    m.clock.text = snClockHM()
    m.footer.text = "mode=" + asStr(s.mode) + "   refreshed " + snClockHMS()
end sub
