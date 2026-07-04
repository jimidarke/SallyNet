' ShowDetailTask — fetch /api/show/<id> and build the seasons/episodes tree + flat queue.

sub init()
    m.top.functionName = "runFetch"
end sub

sub runFetch()
    root = createObject("roSGNode", "ContentNode")
    flat = []
    title = ""

    d = httpGetJson(m.top.showUrl)
    if d <> invalid then
        if d.title <> invalid then title = d.title
        if d.seasons <> invalid then
            for each se in d.seasons
                row = root.createChild("ContentNode")
                if se.title <> invalid then
                    row.title = se.title
                else
                    row.title = "Season " + snFmtInt(se.season)
                end if
                if se.episodes <> invalid then
                    for each ep in se.episodes
                        n = row.createChild("ContentNode")
                        n.title = episodeCaption(ep)
                        n.hdPosterUrl = snMediaItemUrl(ep.still)
                        n.url = snMediaItemUrl(ep.url)
                        n.streamFormat = "mp4"
                        if ep.durationSec <> invalid then n.length = snParseInt(ep.durationSec)
                        if ep.id <> invalid then n.id = ep.id
                        flat.push(snItemAssocFromNode(n))
                    end for
                end if
            end for
        end if
    end if

    m.top.showDetail = root
    m.top.episodesFlat = flat
    m.top.showTitle = title
    m.top.ok = true
    slEvent("show_detail", { seasons: root.getChildCount(), episodes: flat.count() })
end sub

' "S01E03 · Daddy Robot" (either part optional).
function episodeCaption(ep as object) as string
    code = ""
    if ep.season <> invalid and ep.episode <> invalid then
        code = "S" + pad2(snParseInt(ep.season)) + "E" + pad2(snParseInt(ep.episode))
    end if
    t = ""
    if ep.title <> invalid then t = ep.title
    if code <> "" and t <> "" then return code + " · " + t
    if code <> "" then return code
    return t
end function
