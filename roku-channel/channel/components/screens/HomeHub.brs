sub init()
    m.tilesGroup = m.top.findNode("tiles")
    m.ribbon = m.top.findNode("ribbon")
    m.tiles = []

    defs = [
        { label: "Drive",   route: "drive",   enabled: true },
        { label: "Media",   route: "media",   enabled: true },
        { label: "Photos",  route: "photos",  enabled: true },
        { label: "Camp",    route: "camp",    enabled: false },
        { label: "Cameras", route: "cameras", enabled: false },
        { label: "Systems", route: "systems", enabled: false }
    ]
    for each d in defs
        tile = createObject("roSGNode", "NavTile")
        tile.tileLabel = d.label
        tile.route = d.route
        tile.enabled = d.enabled
        m.tilesGroup.appendChild(tile)
        m.tiles.push(tile)
    end for

    m.focusIndex = 0
    applyTileFocus()
end sub

sub applyTileFocus()
    for i = 0 to m.tiles.count() - 1
        m.tiles[i].focused = (i = m.focusIndex)
    end for
end sub

function onKeyEvent(key as string, press as boolean) as boolean
    if not press then return false
    if key = "left" then
        if m.focusIndex > 0 then
            m.focusIndex = m.focusIndex - 1
            applyTileFocus()
        end if
        return true
    else if key = "right" then
        if m.focusIndex < m.tiles.count() - 1 then
            m.focusIndex = m.focusIndex + 1
            applyTileFocus()
        end if
        return true
    else if key = "OK" then
        tile = m.tiles[m.focusIndex]
        m.top.selectedRoute = ""
        if tile.enabled = true then
            m.top.selectedRoute = tile.route
        else
            m.top.selectedRoute = "toast:" + tile.tileLabel
        end if
        return true
    end if
    return false
end function

sub onState()
    s = m.top.state
    if s = invalid then return
    parts = []
    gps = s.gps
    if gps <> invalid then
        if gps.fix = true then
            parts.push("GPS fix " + snFmtInt(gps.sats) + " sats")
            parts.push("Speed " + snFmt1(gps.speed_kmh) + " km/h")
        else
            parts.push("GPS no fix")
        end if
    end if
    drive = s.drive
    if drive <> invalid and drive.km_from_home <> invalid then
        parts.push(snFmt1(drive.km_from_home) + " km from home")
    end if
    if s.mode <> invalid then parts.push("mode " + asStr(s.mode))
    parts.push(snClockHM())
    m.ribbon.text = parts.join("    |    ")
end sub
