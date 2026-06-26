' SallyNet — home-media helpers (catalog row titles + selection projection).
' Pure-ish helpers shared by MediaListTask / MediaScreen. The ContentNode tree itself
' is built on the Task thread (MediaListTask) from /api/media + /api/collections.

' Row header for a collection: "Jasper & the Icefields  ·  Jul 4, 2026  ·  Jasper, AB"
function snRowTitle(c as object) as string
    if c = invalid then return ""
    t = ""
    if c.title <> invalid then t = c.title
    if c.dateStart <> invalid then t = t + "  ·  " + snDateLabelFromIso(c.dateStart)
    if c.place <> invalid and c.place <> "" then t = t + "  ·  " + c.place
    return t
end function

' Project a browse ContentNode (built by MediaListTask) into the plain assocarray
' VodPlayer consumes. Reads only standard ContentNode fields the task set.
function snItemAssocFromNode(n as object) as object
    if n = invalid then return invalid
    return {
        url:       n.url,
        contentid: n.id,
        title:     n.title,
        length:    n.length,
        poster:    n.hdPosterUrl,
        dateLabel: n.shortDescriptionLine1,
        place:     n.shortDescriptionLine2
    }
end function
