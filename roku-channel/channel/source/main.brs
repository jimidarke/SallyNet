' SallyNet — entry point.
' Main(args) receives a deep-link arg map for cold launches and (with
' supports_input_launch=1) hot ECP /input pushes while the channel stays alive.

sub Main(args as dynamic)
    screen = createObject("roSGScreen")
    port = createObject("roMessagePort")
    screen.setMessagePort(port)
    scene = screen.createScene("MainScene")
    screen.show()

    if args = invalid or type(args) <> "roAssociativeArray" then
        scene.args = {}
    else
        scene.args = args
    end if
    slEvent("launch", { args: snFormatArgs(args) })

    while true
        msg = wait(0, port)
        if type(msg) = "roSGScreenEvent" then
            if msg.isScreenClosed() then return
        end if
    end while
end sub

function snFormatArgs(args as dynamic) as string
    if args = invalid or type(args) <> "roAssociativeArray" then return "{}"
    parts = []
    for each k in args
        parts.push(k + "=" + args[k].toStr())
    end for
    return "{" + parts.join(",") + "}"
end function
