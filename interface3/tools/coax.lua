-- Wireshark dissector for IBM 3270 coax frames captured by interface3.
--
-- Captures are written by tools/coax-capture with link type USER0; see
-- CAPTURE.md for the frame layout.

local coax = Proto("coax", "IBM 3270 Coax")

local HEADER_LEN = 6

local FLAG_FROM_TERMINAL = 0x01
local FLAG_TRUNCATED     = 0x02
local FLAG_TIMEOUT       = 0x04
local FLAG_RX_ERROR      = 0x08
local FLAG_INFERRED      = 0x10

local commands = {
    [0x01] = "POLL",
    [0x02] = "RESET",
    [0x03] = "READ_DATA",
    [0x04] = "LOAD_ADDRESS_COUNTER_HI",
    [0x05] = "READ_ADDRESS_COUNTER_HI",
    [0x06] = "CLEAR",
    [0x07] = "READ_EXTENDED_ID",
    [0x08] = "START_OPERATION",
    [0x09] = "READ_TERMINAL_ID",
    [0x0a] = "LOAD_CONTROL_REGISTER",
    [0x0b] = "READ_MULTIPLE",
    [0x0c] = "WRITE_DATA",
    [0x0d] = "READ_STATUS",
    [0x0e] = "INSERT_BYTE",
    [0x10] = "SEARCH_FORWARD",
    [0x11] = "POLL_ACK",
    [0x12] = "SEARCH_BACKWARD",
    [0x14] = "LOAD_ADDRESS_COUNTER_LO",
    [0x15] = "READ_ADDRESS_COUNTER_LO",
    [0x16] = "LOAD_MASK",
    [0x1a] = "LOAD_SECONDARY_CONTROL",
    [0x1c] = "DIAGNOSTIC_RESET",
}

local feature_commands = {
    [0x03] = "EAB_READ_DATA",
    [0x06] = "EAB_LOAD_MASK",
    [0x07] = "READ_FEATURE_ID",
    [0x0a] = "EAB_WRITE_ALTERNATE",
    [0x0b] = "EAB_READ_MULTIPLE",
    [0x0c] = "EAB_WRITE_UNDER_MASK",
    [0x0d] = "EAB_READ_STATUS",
}

local poll_actions = {
    [0x0] = "none",
    [0x1] = "disable keyboard clicker",
    [0x2] = "alarm",
    [0x3] = "enable keyboard clicker",
}

local directions = {
    [0] = "controller to terminal",
    [1] = "terminal to controller",
}

local f_version   = ProtoField.uint8("coax.version", "Version", base.DEC)
local f_port      = ProtoField.uint8("coax.port", "Port", base.DEC)
local f_flags     = ProtoField.uint8("coax.flags", "Flags", base.HEX)
local f_dir       = ProtoField.uint8("coax.direction", "Direction", base.DEC, directions, FLAG_FROM_TERMINAL)
local f_truncated = ProtoField.bool("coax.truncated", "Truncated", 8, nil, FLAG_TRUNCATED)
local f_timeout   = ProtoField.bool("coax.timeout", "Timeout", 8, nil, FLAG_TIMEOUT)
local f_rx_error  = ProtoField.bool("coax.rx_error", "Receive error", 8, nil, FLAG_RX_ERROR)
local f_inferred  = ProtoField.bool("coax.inferred", "Direction inferred", 8, nil, FLAG_INFERRED)
local f_addr      = ProtoField.uint8("coax.addr", "3299 address", base.DEC)
local f_count     = ProtoField.uint16("coax.word_count", "Words", base.DEC)

local f_word      = ProtoField.uint16("coax.word", "Word", base.HEX)
local f_cmd       = ProtoField.uint8("coax.command", "Command", base.HEX, commands)
local f_poll_act  = ProtoField.uint8("coax.poll_action", "Poll action", base.HEX, poll_actions)
local f_feat_cmd  = ProtoField.uint8("coax.feature_command", "Feature command", base.HEX, feature_commands)
local f_feat_addr = ProtoField.uint8("coax.feature_address", "Feature address", base.DEC)
local f_data      = ProtoField.uint8("coax.data", "Data", base.HEX)
local f_parity    = ProtoField.uint8("coax.parity", "Parity bit", base.DEC)
local f_payload   = ProtoField.bytes("coax.payload", "Data bytes")
local f_ttar      = ProtoField.bool("coax.ttar", "Transmission turnaround")
local f_scan_code = ProtoField.uint8("coax.scan_code", "Scan code", base.HEX)
local f_por       = ProtoField.bool("coax.power_on_reset", "Power on reset complete")
local f_continues = ProtoField.uint8("coax.continues", "Continues command", base.HEX, commands)
local f_command_in = ProtoField.framenum("coax.command_in", "Command in frame", base.NONE, frametype.NONE)
local f_request   = ProtoField.framenum("coax.request_in", "Request in frame", base.NONE, frametype.REQUEST)
local f_response  = ProtoField.framenum("coax.response_in", "Response in frame", base.NONE, frametype.RESPONSE)

coax.fields = {
    f_version, f_port, f_flags, f_dir, f_truncated, f_timeout, f_rx_error,
    f_inferred, f_addr, f_count, f_word, f_cmd, f_poll_act, f_feat_cmd, f_feat_addr,
    f_data, f_parity, f_payload, f_ttar, f_scan_code, f_por,
    f_continues, f_command_in, f_request, f_response,
}

local e_parity    = ProtoExpert.new("coax.parity_mismatch", "Data word parity does not match",
                                    expert.group.CHECKSUM, expert.severity.NOTE)
local e_timeout   = ProtoExpert.new("coax.no_response", "Terminal did not respond",
                                    expert.group.RESPONSE_CODE, expert.severity.WARN)
local e_rx_error  = ProtoExpert.new("coax.receive_error", "Reception failed",
                                    expert.group.MALFORMED, expert.severity.ERROR)
local e_truncated = ProtoExpert.new("coax.cut_short", "Frame truncated by the capture",
                                    expert.group.UNDECODED, expert.severity.NOTE)

coax.experts = { e_parity, e_timeout, e_rx_error, e_truncated }

-- Odd parity: set so that the byte plus the parity bit hold an odd number
-- of one bits.  Terminals predating the 3279 leave the bit clear.
local function odd_parity(byte)
    local ones = 0
    for bit = 0, 7 do
        if bit32 and bit32.band(byte, 2 ^ bit) ~= 0 then
            ones = ones + 1
        elseif not bit32 and (math.floor(byte / 2 ^ bit) % 2) == 1 then
            ones = ones + 1
        end
    end
    if ones % 2 == 0 then return 1 end
    return 0
end

-- The outbound command each port last sent, so a response can be read in
-- its light, and so a frame of bare data words can be shown as the
-- continuation of the write it belongs to.  Filled on the first pass and
-- remembered per frame number.
local port_state = {}
local port_command = {}
local frame_request = {}
local frame_response = {}
local frame_continues = {}

function coax.init()
    port_state = {}
    port_command = {}
    frame_request = {}
    frame_response = {}
    frame_continues = {}
end

local function describe_command(word)
    local command = math.floor(word / 4) % 32
    return command, commands[command]
end

local function dissect_command_word(tree, range, word)
    local command, name = describe_command(word)
    local item = tree:add(f_word, range, word)
    item:append_text(string.format(" — command %s", name or string.format("unknown 0x%02x", command)))
    item:add(f_cmd, range, command)

    if command == 0x01 then
        local action = math.floor(word / 256) % 4
        item:add(f_poll_act, range, action)
        if action ~= 0 then
            item:append_text(string.format(", %s", poll_actions[action]))
        end
    end

    -- A feature command carries the feature address in the top four bits,
    -- which no base command reaches.
    local address = math.floor(word / 64) % 16
    if address >= 2 then
        local feature = math.floor(word / 4) % 16
        if feature_commands[feature] then
            local sub = item:add(f_feat_cmd, range, feature)
            sub:append_text(string.format(" (if addressed to a feature)"))
            item:add(f_feat_addr, range, address)
        end
    end

    return command, name
end

local function dissect_data_word(tree, range, word, bytes)
    local byte = math.floor(word / 4) % 256
    local parity = math.floor(word / 2) % 2

    local item = tree:add(f_word, range, word)
    item:append_text(string.format(" — data 0x%02x", byte))
    item:add(f_data, range, byte)
    local parity_item = item:add(f_parity, range, parity)

    if parity ~= 0 and parity ~= odd_parity(byte) then
        parity_item:add_proto_expert_info(e_parity)
    end

    bytes[#bytes + 1] = string.format("%02x", byte)
    return byte
end

local function dissect_poll_response(tree, range, word)
    if word == 0x0a then
        tree:add(f_por, range, true)
        return "power on reset complete"
    end
    if (word % 4) == 2 then
        local scan_code = math.floor(word / 4) % 256
        tree:add(f_scan_code, range, scan_code)
        return string.format("keystroke 0x%02x", scan_code)
    end
    return string.format("poll response 0x%03x", word)
end

function coax.dissector(tvb, pinfo, tree)
    local length = tvb:len()
    if length < HEADER_LEN then return 0 end

    pinfo.cols.protocol = "COAX"

    local version = tvb(0, 1):uint()
    local port = tvb(1, 1):uint()
    local flags = tvb(2, 1):uint()
    local addr = tvb(3, 1):uint()
    local count = tvb(4, 2):uint()

    local from_terminal = (flags % 2) == 1

    local root = tree:add(coax, tvb(), string.format("IBM 3270 Coax, port %d, %s%s",
                                                     port,
                                                     from_terminal and "from terminal" or "to terminal",
                                                     bit.band(flags, FLAG_INFERRED) ~= 0 and " (inferred)" or ""))
    root:add(f_version, tvb(0, 1), version)
    root:add(f_port, tvb(1, 1), port)
    local flags_tree = root:add(f_flags, tvb(2, 1), flags)
    flags_tree:add(f_dir, tvb(2, 1), flags)
    flags_tree:add(f_truncated, tvb(2, 1), flags)
    flags_tree:add(f_timeout, tvb(2, 1), flags)
    flags_tree:add(f_rx_error, tvb(2, 1), flags)
    flags_tree:add(f_inferred, tvb(2, 1), flags)
    if addr ~= 0xff then
        root:add(f_addr, tvb(3, 1), addr)
    end
    root:add(f_count, tvb(4, 2), count)

    -- Pair a response with the command it answers.
    if not pinfo.visited then
        if from_terminal then
            local pending = port_state[port]
            if pending then
                frame_request[pinfo.number] = pending
                frame_response[pending.frame] = pinfo.number
                port_state[port] = nil
            end
        elseif count > 0 and length >= HEADER_LEN + 2 then
            local first = tvb(HEADER_LEN, 2):uint()
            if first % 2 == 1 then
                local command = describe_command(first)
                port_command[port] = { command = command, frame = pinfo.number }
            elseif port_command[port] then
                -- A long write is split into several frames; the terminal
                -- keeps writing at its address counter, so the command word
                -- appears only in the first of them.
                frame_continues[pinfo.number] = port_command[port]
            end
            local carried = port_command[port]
            port_state[port] = { frame = pinfo.number,
                                 command = carried and carried.command }
        end
    end

    local request = frame_request[pinfo.number]
    local summary

    if bit.band(flags, FLAG_TIMEOUT) ~= 0 then
        root:add_proto_expert_info(e_timeout)
        summary = "no response"
    elseif bit.band(flags, FLAG_RX_ERROR) ~= 0 then
        root:add_proto_expert_info(e_rx_error)
        summary = "receive error"
    end

    if bit.band(flags, FLAG_TRUNCATED) ~= 0 then
        root:add_proto_expert_info(e_truncated)
    end

    local available = math.floor((length - HEADER_LEN) / 2)
    local words = root
    local bytes = {}
    local command_name

    if available > 0 then
        words = root:add(coax, tvb(HEADER_LEN, available * 2),
                         string.format("Words (%d of %d)", available, count))
    end

    for index = 0, available - 1 do
        local offset = HEADER_LEN + index * 2
        local range = tvb(offset, 2)
        local word = range:uint()

        if word == 0 and available == 1 then
            local item = words:add(f_word, range, word)
            item:append_text(" — transmission turnaround")
            words:add(f_ttar, range, true):set_generated()
            summary = summary or "TT/AR"
        elseif from_terminal and index == 0 and request and request.command == 0x01
               and available == 1 then
            local item = words:add(f_word, range, word)
            summary = dissect_poll_response(item, range, word)
            item:append_text(" — " .. summary)
        elseif (word % 2) == 1 then
            local _, name = dissect_command_word(words, range, word)
            command_name = command_name or name
        else
            dissect_data_word(words, range, word, bytes)
        end
    end

    if #bytes > 0 then
        -- The data bytes are spread over the low eight bits of the words,
        -- so they get their own byte view to be read as a block.
        local blob = ByteArray.new(table.concat(bytes)):tvb("Coax data")
        words:add(f_payload, blob()):set_generated()
    end

    local continues = frame_continues[pinfo.number]
    if continues then
        root:add(f_continues, continues.command):set_generated()
        root:add(f_command_in, continues.frame):set_generated()
    end

    if request then
        root:add(f_request, request.frame):set_generated()
    end
    if frame_response[pinfo.number] then
        root:add(f_response, frame_response[pinfo.number]):set_generated()
    end

    local function plural(n, noun)
        if n == 1 then return string.format("%d %s", n, noun) end
        return string.format("%d %ss", n, noun)
    end

    if not summary then
        if command_name then
            summary = command_name
            if #bytes > 0 then
                summary = string.format("%s, %s", command_name, plural(#bytes, "byte"))
            end
        elseif continues then
            summary = string.format("%s continued, %s",
                                    commands[continues.command]
                                        or string.format("command 0x%02x", continues.command),
                                    plural(#bytes, "byte"))
        elseif #bytes > 0 and request and request.command and commands[request.command] then
            summary = string.format("%s response, %s", commands[request.command],
                                    plural(#bytes, "byte"))
        elseif #bytes > 0 then
            summary = plural(#bytes, "data byte")
        else
            summary = plural(count, "word")
        end
    end

    if bit.band(flags, FLAG_TRUNCATED) ~= 0 then
        summary = summary .. " [truncated]"
    end

    pinfo.cols.info = string.format("coax%d %s %s", port,
                                    from_terminal and "<" or ">", summary)

    return length
end

local encap = DissectorTable.get("wtap_encap")
encap:add(wtap.USER0, coax)
