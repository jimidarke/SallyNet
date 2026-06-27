sub init()
    m.place = m.top.findNode("place")
    m.sub = m.top.findNode("sub")
    m.aboard = m.top.findNode("aboard")
    m.fromhome = m.top.findNode("fromhome")
    m.gps = m.top.findNode("gps")
    m.clock = m.top.findNode("clock")
    m.footer = m.top.findNode("footer")
end sub

sub onState()
    s = m.top.state
    if s = invalid then return

    trip = s.trip
    if trip <> invalid then
        place = trip.destName
        if place = invalid then place = trip.title
        m.place.text = asStr(place)

        ' subline: trip name + date range + day-N
        bits = []
        if trip.title <> invalid then bits.push(asStr(trip.title))
        if trip.dateStart <> invalid then
            span = snDateLabelFromIso(trip.dateStart)
            if trip.dateEnd <> invalid then span = span + " - " + snDateLabelFromIso(trip.dateEnd)
            day = snDaysSinceIso(trip.dateStart)
            if day > 0 then span = span + "   (day " + day.toStr() + ")"
            bits.push(span)
        end if
        m.sub.text = bits.join("    |    ")

        ab = trip.aboard
        if ab <> invalid and ab.count() > 0 then
            m.aboard.text = ab.join(", ")
        else
            m.aboard.text = "--"
        end if
    else
        m.place.text = "No active trip"
        m.sub.text = ""
        m.aboard.text = ""
    end if

    drive = s.drive
    if drive <> invalid and drive.km_from_home <> invalid then
        m.fromhome.text = "From home   " + snFmt1(drive.km_from_home) + " km"
    end if

    gps = s.gps
    if gps <> invalid then
        hasFix = (gps.fix = true)
        m.gps.text = "GPS   " + iif(hasFix, "fix - " + snFmtInt(gps.sats) + " sats", "no fix")
    end if

    m.clock.text = snClockHM()
    m.footer.text = "mode=" + asStr(s.mode) + "   refreshed " + snClockHMS()
end sub
