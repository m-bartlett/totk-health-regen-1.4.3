from __future__ import annotations

import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from totk_zs import ZsHelper  # noqa: E402
import oead  # noqa: E402
import ainb  # noqa: E402
import byml7_patch  # noqa: E402


def int_input(name, *, node_index=-1, default=0, flags=None):
    if flags is None:
        flags = ["Uses Default"] if node_index == -1 else []
    return {"Name": name, "Default Value": default, "Node Index": node_index,
            "Output Index": 0, "Flags": flags}


def int_input_bool(name, *, node_index):
    return {"Name": name, "Default Value": False, "Node Index": node_index,
            "Output Index": 0, "Flags": []}


def blackboard_set_s32(key, *, value_node_index, value_default=0, execute_every_frame=True):
    return {
        "Properties": {
            "Int": [{"Name": "BlackboardType", "Default Value": 0, "Flags": []}],
            "Bool": [
                {"Name": "ExecuteOnce", "Default Value": not execute_every_frame, "Flags": []},
                {"Name": "IsIgnoreNotExistsError", "Default Value": False, "Flags": []},
            ],
            "String": [{"Name": "BlackboardKey", "Default Value": key, "Flags": []}],
        },
        "Parameters": {
            "Inputs": {"Int": [int_input("S32", node_index=value_node_index, default=value_default)]},
            "Outputs": {},
        },
    }


def build_nocalcskip_ainb(ticks_per_heal: int, heal_amount: int, template_ainb_bytes: bytes):
    """Builds AI/Player.NoCalcSkipUtility.root.ainb from scratch (there is
    no vanilla version of this file to start from - it's new).

    template_ainb_bytes should be the user's own copy of the stock
    AI/Player.brain.root.ainb (read from --romfs at build time, never
    bundled with this project) - only its generic schema/header fields
    (Version, Blackboard ID, etc.) are reused, as a template for building
    a well-formed AINB file from scratch; its actual Nodes/Commands/
    Blackboard are fully replaced below.
    """

    # Node layout, mirroring the reverse-engineered reference mod 1:1 in
    # structure (only the timer storage mechanism differs: Blackboard
    # instead of persistent GameData).
    (
        N_ROOT, N_FULL_SELECT, N_THRESH_SELECT, N_HEAL_GROUP,
        N_GET_STATUS, N_GET_LIFE, N_GET_MAXLIFE, N_LIFE_EQ_MAX,
        N_GET_TIMER, N_TIMER_EQ_THRESHOLD, N_RESET_TIMER_FULL,
        N_TIMER_PLUS1, N_STORE_TIMER_INC,
        N_NEW_LIFE_RAW, N_NEW_LIFE, N_RESET_TIMER_HEAL, N_SET_LIFE,
        N_GET_EXTRALIFE, N_GET_BREAKLIFE,
    ) = range(19)

    nodes = []

    nodes.append({
        "Node Type": "Element_Simultaneous",
        "Node Index": N_ROOT,
        "Name": "",
        "GUID": "a6ea0001-0000-4000-8000-000000000000",
        "Flags": ["Is Root Node"],
        "Queries": [],
        "Attachments": [],
        "Properties": {
            "Int": [
                {"Name": "EndPolicy", "Default Value": 0, "Flags": []},
                {"Name": "ResultPolicy", "Default Value": 0, "Flags": []},
            ]
        },
        "Parameters": {"Inputs": {}, "Outputs": {}},
        "XLink Actions": [],
        "Plugs": {"Child": [{"Node Index": N_FULL_SELECT, "Name": ""}]},
    })

    nodes.append({
        "Node Type": "Element_BoolSelector",
        "Node Index": N_FULL_SELECT,
        "Name": "",
        "GUID": "a6ea0002-0000-4000-8000-000000000000",
        "Flags": [],
        "Queries": [N_LIFE_EQ_MAX],
        "Attachments": [],
        "Properties": {
            "Int": [{"Name": "CalculateTiming", "Default Value": 0, "Flags": []}],
            "Bool": [
                {"Name": "ChildFrameSync", "Default Value": False, "Flags": []},
                {"Name": "InputValue", "Default Value": False, "Flags": []},
                {"Name": "IsNoSelectWhenChildBusy", "Default Value": False, "Flags": []},
            ],
        },
        "Parameters": {"Inputs": {"Bool": [int_input_bool("Input", node_index=N_LIFE_EQ_MAX)]}, "Outputs": {}},
        "XLink Actions": [],
        "Plugs": {
            "Generic": [{"Node Index": N_LIFE_EQ_MAX, "Name": "Input", "Unknown 1": 0, "Unknown 2": 0}],
            "Child": [
                {"Node Index": N_RESET_TIMER_FULL, "Name": "True"},
                {"Node Index": N_THRESH_SELECT, "Name": "False"},
            ],
        },
    })

    nodes.append({
        "Node Type": "Element_BoolSelector",
        "Node Index": N_THRESH_SELECT,
        "Name": "",
        "GUID": "a6ea0003-0000-4000-8000-000000000000",
        "Flags": [],
        "Queries": [N_TIMER_EQ_THRESHOLD],
        "Attachments": [],
        "Properties": {
            "Int": [{"Name": "CalculateTiming", "Default Value": 0, "Flags": []}],
            "Bool": [
                {"Name": "ChildFrameSync", "Default Value": False, "Flags": []},
                {"Name": "InputValue", "Default Value": False, "Flags": []},
                {"Name": "IsNoSelectWhenChildBusy", "Default Value": False, "Flags": []},
            ],
        },
        "Parameters": {"Inputs": {"Bool": [int_input_bool("Input", node_index=N_TIMER_EQ_THRESHOLD)]}, "Outputs": {}},
        "XLink Actions": [],
        "Plugs": {
            "Generic": [{"Node Index": N_TIMER_EQ_THRESHOLD, "Name": "Input", "Unknown 1": 0, "Unknown 2": 0}],
            "Child": [
                {"Node Index": N_HEAL_GROUP, "Name": "True"},
                {"Node Index": N_STORE_TIMER_INC, "Name": "False"},
            ],
        },
    })

    nodes.append({
        "Node Type": "Element_Simultaneous",
        "Node Index": N_HEAL_GROUP,
        "Name": "",
        "GUID": "a6ea0004-0000-4000-8000-000000000000",
        "Flags": [],
        "Queries": [],
        "Attachments": [],
        "Properties": {
            "Int": [
                {"Name": "EndPolicy", "Default Value": 0, "Flags": []},
                {"Name": "ResultPolicy", "Default Value": 0, "Flags": []},
            ]
        },
        "Parameters": {"Inputs": {}, "Outputs": {}},
        "XLink Actions": [],
        "Plugs": {"Child": [
            {"Node Index": N_SET_LIFE, "Name": ""},
            {"Node Index": N_RESET_TIMER_HEAL, "Name": ""},
        ]},
    })

    nodes.append({
        "Node Type": "UserDefined",
        "Node Index": N_GET_STATUS,
        "Name": "QueryGetNonStructGameDataStruct",
        "GUID": "a6ea0005-0000-4000-8000-000000000000",
        "Flags": ["Is Query"],
        "Queries": [],
        "Attachments": [],
        "Properties": {
            "Bool": [
                {"Name": "DispError", "Default Value": False, "Flags": []},
                {"Name": "OutputOnlyOnEnter", "Default Value": False, "Flags": []},
            ]
        },
        "Parameters": {
            "Inputs": {
                "Int": [int_input("GameDataIndex", default=0)],
                "String": [{"Name": "GameDataFullName", "Default Value": "PlayerStatus",
                            "Node Index": -1, "Output Index": 0, "Flags": ["Uses Default"]}],
            },
            "Outputs": {"Pointer": [{"Name": "Value", "Classname": "const void", "Is Output": True}]},
        },
        "XLink Actions": [],
        "Plugs": {"Generic": [
            {"Node Index": N_GET_LIFE, "Name": "Value"},
            {"Node Index": N_GET_MAXLIFE, "Name": "Value"},
            {"Node Index": N_GET_EXTRALIFE, "Name": "Value"},
            {"Node Index": N_GET_BREAKLIFE, "Name": "Value"},
        ]},
    })

    def get_game_data_int(node_index, name, feeds, guid_suffix):
        return {
            "Node Type": "UserDefined",
            "Node Index": node_index,
            "Name": "QueryGetGameDataInt",
            "GUID": f"a6ea0006-0000-4000-8000-0000000000{guid_suffix:02x}",
            "Flags": ["Is Query"],
            "Queries": [N_GET_STATUS],
            "Attachments": [],
            "Properties": {
                "Bool": [
                    {"Name": "DispError", "Default Value": False, "Flags": []},
                    {"Name": "OutputOnlyOnEnter", "Default Value": False, "Flags": []},
                ]
            },
            "Parameters": {
                "Inputs": {
                    "Int": [int_input("GameDataIndex", default=0)],
                    "String": [{"Name": "GameDataName", "Default Value": name,
                                "Node Index": -1, "Output Index": 0, "Flags": ["Uses Default"]}],
                    "Pointer": [{"Name": "ParentStruct", "Classname": "const void", "Default Value": None,
                                 "Node Index": N_GET_STATUS, "Output Index": 0, "Flags": []}],
                },
                "Outputs": {"Int": [{"Name": "Value", "Is Output": True}]},
            },
            "XLink Actions": [],
            "Plugs": {"Generic": [{"Node Index": f, "Name": "Value"} for f in feeds]},
        }

    nodes.append(get_game_data_int(N_GET_LIFE, "Life", [N_LIFE_EQ_MAX, N_NEW_LIFE_RAW], 0x01))
    nodes.append(get_game_data_int(N_GET_MAXLIFE, "MaxLife", [N_LIFE_EQ_MAX, N_NEW_LIFE], 0x02))
    nodes.append(get_game_data_int(N_GET_EXTRALIFE, "ExtraLife", [N_SET_LIFE], 0x03))
    nodes.append(get_game_data_int(N_GET_BREAKLIFE, "BreakLife", [N_SET_LIFE], 0x04))

    nodes.append({
        "Node Type": "UserDefined",
        "Node Index": N_LIFE_EQ_MAX,
        "Name": "QueryMathEqualS32",
        "GUID": "a6ea0007-0000-4000-8000-000000000000",
        "Flags": ["Is Query"],
        "Queries": [N_GET_LIFE, N_GET_MAXLIFE],
        "Attachments": [],
        "Properties": {"Bool": [{"Name": "OutputOnlyOnEnter", "Default Value": False, "Flags": []}]},
        "Parameters": {
            "Inputs": {
                "Int": [
                    int_input("S32", node_index=N_GET_LIFE, flags=[]),
                    int_input("S32Base", node_index=N_GET_MAXLIFE, flags=[]),
                ]
            },
            "Outputs": {"Bool": [{"Name": "Bool", "Is Output": True}]},
        },
        "XLink Actions": [],
        "Plugs": {},
    })

    nodes.append({
        "Node Type": "UserDefined",
        "Node Index": N_GET_TIMER,
        "Name": "QueryBlackboardGetS32",
        "GUID": "a6ea0008-0000-4000-8000-000000000000",
        "Flags": ["Is Query"],
        "Queries": [],
        "Attachments": [],
        "Properties": {
            "Int": [{"Name": "BlackboardType", "Default Value": 0, "Flags": []}],
            "Bool": [{"Name": "OutputOnlyOnEnter", "Default Value": False, "Flags": []}],
            "String": [{"Name": "BlackboardKey", "Default Value": "AmbientHealingTimer", "Flags": []}],
        },
        "Parameters": {"Inputs": {}, "Outputs": {"Int": [{"Name": "S32", "Is Output": True}]}},
        "XLink Actions": [],
        "Plugs": {"Generic": [
            {"Node Index": N_TIMER_EQ_THRESHOLD, "Name": "S32"},
            {"Node Index": N_TIMER_PLUS1, "Name": "S32"},
        ]},
    })

    nodes.append({
        "Node Type": "UserDefined",
        "Node Index": N_TIMER_EQ_THRESHOLD,
        "Name": "QueryMathEqualS32",
        "GUID": "a6ea0009-0000-4000-8000-000000000000",
        "Flags": ["Is Query"],
        "Queries": [N_GET_TIMER],
        "Attachments": [],
        "Properties": {"Bool": [{"Name": "OutputOnlyOnEnter", "Default Value": False, "Flags": []}]},
        "Parameters": {
            "Inputs": {
                "Int": [
                    int_input("S32", node_index=N_GET_TIMER, flags=[]),
                    int_input("S32Base", default=ticks_per_heal),
                ]
            },
            "Outputs": {"Bool": [{"Name": "Bool", "Is Output": True}]},
        },
        "XLink Actions": [],
        "Plugs": {},
    })

    nodes.append({
        "Node Type": "UserDefined",
        "Node Index": N_RESET_TIMER_FULL,
        "Name": "ExecuteBlackboardSetS32",
        "GUID": "a6ea000a-0000-4000-8000-000000000000",
        "Flags": [],
        "Queries": [],
        "Attachments": [],
        "XLink Actions": [],
        "Plugs": {},
        **blackboard_set_s32("AmbientHealingTimer", value_node_index=-1, value_default=0, execute_every_frame=False),
    })

    nodes.append({
        "Node Type": "UserDefined",
        "Node Index": N_TIMER_PLUS1,
        "Name": "QueryMathAddS32",
        "GUID": "a6ea000b-0000-4000-8000-000000000000",
        "Flags": ["Is Query"],
        "Queries": [N_GET_TIMER],
        "Attachments": [],
        "Properties": {"Bool": [{"Name": "OutputOnlyOnEnter", "Default Value": False, "Flags": []}]},
        "Parameters": {
            "Inputs": {
                "Int": [
                    int_input("InputA", node_index=N_GET_TIMER, flags=[]),
                    int_input("InputB", default=1),
                ]
            },
            "Outputs": {"Int": [{"Name": "Result", "Is Output": True}]},
        },
        "XLink Actions": [],
        "Plugs": {"Generic": [{"Node Index": N_STORE_TIMER_INC, "Name": "Result"}]},
    })

    nodes.append({
        "Node Type": "UserDefined",
        "Node Index": N_STORE_TIMER_INC,
        "Name": "ExecuteBlackboardSetS32",
        "GUID": "a6ea000c-0000-4000-8000-000000000000",
        "Flags": [],
        "Queries": [N_TIMER_PLUS1],
        "Attachments": [],
        "XLink Actions": [],
        "Plugs": {},
        **blackboard_set_s32("AmbientHealingTimer", value_node_index=N_TIMER_PLUS1, execute_every_frame=True),
    })

    nodes.append({
        "Node Type": "UserDefined",
        "Node Index": N_NEW_LIFE_RAW,
        "Name": "QueryMathAddS32",
        "GUID": "a6ea000d-0000-4000-8000-000000000000",
        "Flags": ["Is Query"],
        "Queries": [N_GET_LIFE],
        "Attachments": [],
        "Properties": {"Bool": [{"Name": "OutputOnlyOnEnter", "Default Value": False, "Flags": []}]},
        "Parameters": {
            "Inputs": {
                "Int": [
                    int_input("InputA", node_index=N_GET_LIFE, flags=[]),
                    int_input("InputB", default=heal_amount),
                ]
            },
            "Outputs": {"Int": [{"Name": "Result", "Is Output": True}]},
        },
        "XLink Actions": [],
        "Plugs": {"Generic": [{"Node Index": N_NEW_LIFE, "Name": "Result"}]},
    })

    nodes.append({
        "Node Type": "UserDefined",
        "Node Index": N_NEW_LIFE,
        "Name": "QueryMathClampS32",
        "GUID": "a6ea0010-0000-4000-8000-000000000000",
        "Flags": ["Is Query"],
        "Queries": [N_NEW_LIFE_RAW, N_GET_MAXLIFE],
        "Attachments": [],
        "Properties": {"Bool": [{"Name": "OutputOnlyOnEnter", "Default Value": False, "Flags": []}]},
        "Parameters": {
            "Inputs": {
                "Int": [
                    int_input("Max", node_index=N_GET_MAXLIFE, flags=[]),
                    int_input("Min", default=0),
                    int_input("Value", node_index=N_NEW_LIFE_RAW, flags=[]),
                ]
            },
            "Outputs": {"Int": [{"Name": "S32", "Is Output": True}]},
        },
        "XLink Actions": [],
        "Plugs": {"Generic": [{"Node Index": N_SET_LIFE, "Name": "S32"}]},
    })

    nodes.append({
        "Node Type": "UserDefined",
        "Node Index": N_RESET_TIMER_HEAL,
        "Name": "ExecuteBlackboardSetS32",
        "GUID": "a6ea000e-0000-4000-8000-000000000000",
        "Flags": [],
        "Queries": [],
        "Attachments": [],
        "XLink Actions": [],
        "Plugs": {},
        **blackboard_set_s32("AmbientHealingTimer", value_node_index=-1, value_default=0, execute_every_frame=False),
    })

    nodes.append({
        "Node Type": "UserDefined",
        "Node Index": N_SET_LIFE,
        "Name": "OneShotSetLife",
        "GUID": "a6ea000f-0000-4000-8000-000000000000",
        "Flags": [],
        "Queries": [N_GET_BREAKLIFE, N_GET_EXTRALIFE, N_NEW_LIFE],
        "Attachments": [],
        "Properties": {"Bool": [{"Name": "ExecuteEveryFrame", "Default Value": False, "Flags": []}]},
        "Parameters": {
            "Inputs": {
                "Int": [
                    int_input("BreakLife", node_index=N_GET_BREAKLIFE),
                    int_input("ExtraLife", node_index=N_GET_EXTRALIFE),
                    int_input("Life", node_index=N_NEW_LIFE, flags=[]),
                ]
            },
            "Outputs": {},
        },
        "XLink Actions": [],
        "Plugs": {},
    })

    nodes.sort(key=lambda n: n["Node Index"])

    a = ainb.AINB.from_binary(template_ainb_bytes)
    ainb_dict = a.as_dict()
    ainb_dict["Filename"] = "Player.NoCalcSkipUtility.root"
    ainb_dict["Commands"] = [{"Name": "Root", "GUID": "a6ea0000-0000-4000-8000-000000000001",
                               "Root Node Index": N_ROOT}]
    ainb_dict["Nodes"] = nodes
    ainb_dict["Blackboard"] = {"S32": [
        {"Blackboard Index": 0, "Name": "AmbientHealingTimer", "Notes": "",
         "Inherit Mode": "DontInherit", "Default Value": 0},
    ]}

    out = ainb.AINB.from_dict(ainb_dict, override_filename="Player.NoCalcSkipUtility.root")
    data = out.to_binary()

    check = ainb.AINB.from_dict(ainb.AINB.from_dict(ainb_dict).as_dict())
    print("round-trip OK, nodes:", len(check.as_dict()["Nodes"]))
    return data


def parse_args():
    p = argparse.ArgumentParser(description="Build the Ambient Healing mod.")
    p.add_argument("--romfs", required=True,
                    help="Path to a 1.4.3 romfs dump extracted from your own legally "
                         "obtained copy of the game (e.g. '.../TotK 1.4.3/romfs'). "
                         "Required - this project ships no game files.")
    p.add_argument("--out", default=None,
                    help="Output mod directory (default: './output/Ambient Healing v1.4.3' "
                         "relative to the current directory).")
    p.add_argument("--seconds", type=float, default=60.0,
                    help="Real-time seconds between heal pulses (default: 60).")
    p.add_argument("--heal-amount", type=int, default=1,
                    help="Life units (quarter-hearts) healed per pulse (default: 1; 4 = one full heart).")
    p.add_argument("--ticks-per-second", type=float, default=30.0,
                    help="AI tree tick rate, used to convert --seconds to ticks "
                         "(default: 30, taken from the original mod's own 1800-tick "
                         "threshold in its \"Full Heart per 1 Minute\" variant).")
    return p.parse_args()


def main():
    args = parse_args()
    ticks_per_heal = round(args.seconds * args.ticks_per_second)
    if ticks_per_heal < 1:
        raise SystemExit("--seconds/--ticks-per-second must work out to at least 1 tick")

    mod_dir = pathlib.Path(args.out) if args.out else pathlib.Path("output") / "Ambient Healing v1.4.3"
    out_romfs_pack = mod_dir / "romfs" / "Pack" / "Actor" / "Player.pack.zs"

    ref = ZsHelper(args.romfs)

    ref_pack_data = ref.decompress_file("Pack/Actor/Player.pack.zs")
    ref_sarc = oead.Sarc(ref_pack_data)

    template_ainb_bytes = bytes(next(f.data for f in ref_sarc.get_files()
                                      if f.name == "AI/Player.brain.root.ainb"))
    new_ainb_data = build_nocalcskip_ainb(ticks_per_heal, args.heal_amount, template_ainb_bytes)

    writer = oead.SarcWriter(endian=oead.Endianness.Little)
    for f in ref_sarc.get_files():
        # Player.brain.root.ainb is intentionally left untouched (vanilla bytes).
        writer.files[f.name] = bytes(f.data)
    writer.files["AI/Player.NoCalcSkipUtility.root.ainb"] = new_ainb_data

    bsa_name = "Component/BSAParam/Player.game__component__BSAParam.bgyml"
    bsa_data = bytes(next(f.data for f in ref_sarc.get_files() if f.name == bsa_name))
    writer.files[bsa_name] = byml7_patch.set_string_field(
        bsa_data, "NoCalcSkipUtilityAin", "Work/AI/Root/Player.NoCalcSkipUtility.root.ain")

    _, new_pack_data = writer.write()
    compressed = ref.compress(bytes(new_pack_data))
    out_romfs_pack.parent.mkdir(parents=True, exist_ok=True)
    out_romfs_pack.write_bytes(compressed)
    print(f"Wrote {out_romfs_pack}")
    print(f"Expect +{args.heal_amount} life unit(s) every {args.seconds:g}s "
          f"({ticks_per_heal} ticks at {args.ticks_per_second:g} tick/s), repeating.")
    print("Player.brain.root.ainb is untouched - damage/invincibility should behave normally at all times.")


if __name__ == "__main__":
    main()