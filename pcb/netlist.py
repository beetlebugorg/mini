"""Netlist and placement for the Bluespeaker main PCB.

This file is the single source for the schematic and the PCB. build.py reads
it and writes bluespeaker.kicad_sch and bluespeaker.kicad_pcb.

Board coordinates are KiCad coordinates in mm, seen from the top side.
The board is 224 x 46 mm with its top-left corner at (100, 100).
The top side faces the rear of the speaker (+Y in the enclosure model).
The bottom side faces the baffle. On the bottom side: the three key switches
and the LCD connector. All cable connectors are vertical (top entry) and sit
in the upper half of the board, where the bay has free space behind the PCB.
The battery fills the space behind the lower half (Z < 31 mm in the enclosure).

The encoder is not on this board. It sits on a small daughter board behind
the baffle at the knob (see cad/bluespeaker.py), and J6 takes its leads.

Map from the enclosure model (cad x, cad z) to the board:
    kx = 100 + 112 - cad_x
    ky = 100 + 23 - (cad_z - 30)
"""

from dataclasses import dataclass, field

BOARD = dict(x0=100.0, y0=100.0, w=224.0, h=46.0, corner=1.5)


def from_cad(cad_x, cad_z):
    return 100 + 112 - cad_x, 100 + 23 - (cad_z - 30)


@dataclass
class Part:
    ref: str
    value: str
    symbol: str  # "Lib:Name" in pcb/lib/symbols, or "Bluespeaker:Name"
    footprint: str  # "Lib:Name" in pcb/lib
    pos: tuple  # (kx, ky)
    rot: float = 0.0
    side: str = "top"
    nets: dict = field(default_factory=dict)  # pin name or number -> net
    nc: tuple = ()  # pin names or numbers that have no connection
    group: str = ""


def R(ref, value, a, b, pos, rot=0, group=""):
    return Part(ref, value, "Device:R", "Resistor_SMD:R_0603_1608Metric", pos, rot, nets={"1": a, "2": b}, group=group)


def C(ref, value, a, b, pos, size="0603", rot=0, group=""):
    fp = {"0603": "C_0603_1608Metric", "0805": "C_0805_2012Metric", "1206": "C_1206_3216Metric"}[size]
    return Part(ref, value, "Device:C", f"Capacitor_SMD:{fp}", pos, rot, nets={"1": a, "2": b}, group=group)


PARTS = [
    # ------------------------------------------------------------ MCU
    Part("U1", "ESP32-S3-WROOM-1-N16R8", "RF_Module:ESP32-S3-WROOM-1", "RF_Module:ESP32-S3-WROOM-1",
         (113.5, 123.0), rot=90, group="MCU", nets={
             "GND": "GND", "3V3": "+3V3", "EN": "ESP_EN", "IO0": "ESP_BOOT",
             "USB_D-": "USB_DN", "USB_D+": "USB_DP",
             "IO4": "I2S_A_BCLK", "IO5": "I2S_A_LRCK", "IO6": "I2S_A_DOUT", "IO38": "I2S_SEL",
             "IO7": "AMP_PDN", "IO15": "AMP_FAULT",
             "IO16": "BT_RST", "IO17": "BT_RXD", "IO18": "BT_TXD",
             "IO8": "I2C_SDA", "IO9": "I2C_SCL", "IO3": "CHG_INT",
             "IO10": "LCD_CS", "IO11": "LCD_MOSI", "IO12": "LCD_SCK", "IO13": "LCD_DC", "IO14": "LCD_RST",
             "IO21": "LCD_BL", "IO47": "TP_INT", "IO48": "TP_RST",
             "IO1": "ENC_A", "IO2": "ENC_B", "IO42": "ENC_SW",
             "IO39": "KEY_PREV", "IO40": "KEY_PLAY", "IO41": "KEY_NEXT",
         }, nc=("IO35", "IO36", "IO37", "IO45", "IO46", "RXD0", "TXD0")),
    C("C1", "10u", "+3V3", "GND", (131.0, 112.0), "0805", group="MCU"),
    C("C2", "100n", "+3V3", "GND", (131.0, 115.0), group="MCU"),
    R("R1", "10k", "+3V3", "ESP_EN", (131.0, 126.0), group="MCU"),
    C("C3", "1u", "ESP_EN", "GND", (131.0, 129.0), group="MCU"),
    R("R2", "10k", "+3V3", "ESP_BOOT", (131.0, 132.0), group="MCU"),
    R("R3", "4k7", "+3V3", "I2C_SDA", (137.0, 112.0), group="MCU"),
    R("R4", "4k7", "+3V3", "I2C_SCL", (137.0, 115.0), group="MCU"),
    Part("SW4", "RESET", "Switch:SW_Push", "Button_Switch_SMD:SW_SPST_TL3342", (142.5, 141.0), group="MCU",
         nets={"1": "ESP_EN", "2": "GND"}),
    Part("SW5", "BOOT", "Switch:SW_Push", "Button_Switch_SMD:SW_SPST_TL3342", (142.5, 133.5), group="MCU",
         nets={"1": "ESP_BOOT", "2": "GND"}),

    # ------------------------------------------------------------ Bluetooth
    Part("U2", "FSC-BT1026D (placeholder pinout)", "Bluespeaker:FSC-BT1026D", "Bluespeaker:Feasycom_FSC-BT1026D",
         (242.0, 123.0), group="Bluetooth", nets={
             "GND": "GND", "VBAT": "+3V3", "VDD_IO": "+3V3", "RST": "BT_RST",
             "UART_TX": "BT_TXD", "UART_RX": "BT_RXD",
             "I2S_BCLK": "I2S_B_BCLK", "I2S_WS": "I2S_B_LRCK", "I2S_DOUT": "I2S_B_DOUT",
         }, nc=("LED",)),
    C("C4", "10u", "+3V3", "GND", (231.0, 111.0), "0805", group="Bluetooth"),
    C("C5", "100n", "+3V3", "GND", (231.0, 114.0), group="Bluetooth"),

    # ------------------------------------------------------------ I2S source select
    Part("U6", "SN74LVC157APW", "74xx:74LS157", "Package_SO:TSSOP-16_4.4x5mm_P0.65mm", (186.0, 140.0), rot=90,
         group="Audio", nets={
             "S": "I2S_SEL", "E": "GND", "VCC": "+3V3", "GND": "GND",
             "I0a": "I2S_A_BCLK", "I1a": "I2S_B_BCLK", "Za": "AMP_SCLK",
             "I0b": "I2S_A_LRCK", "I1b": "I2S_B_LRCK", "Zb": "AMP_LRCK",
             "I0c": "I2S_A_DOUT", "I1c": "I2S_B_DOUT", "Zc": "AMP_SDIN",
             "I0d": "GND", "I1d": "GND",
         }, nc=("Zd",)),
    C("C6", "100n", "+3V3", "GND", (193.0, 140.0), rot=90, group="Audio"),

    # ------------------------------------------------------------ Amplifier
    Part("U5", "TAS5805MPWPR", "Amplifier_Audio:TAS5805MPWP",
         "Package_SO:TSSOP-28-1EP_4.4x9.7mm_P0.65mm_EP3.4x9.7mm_Mask3.1x4.05mm_ThermalVias",
         (165.0, 123.0), group="Audio", nets={
             "DVDD": "+3V3", "DGND": "GND", "AGND": "GND", "PGND": "GND", "EP": "GND",
             "PVDD": "VSYS", "AVDD": "AMP_AVDD", "VR_DIG": "AMP_VRDIG",
             "SCLK": "AMP_SCLK", "LRCLK": "AMP_LRCK", "SDIN": "AMP_SDIN",
             "SDA": "I2C_SDA", "SCL": "I2C_SCL", "~{PDN}": "AMP_PDN", "ADR/~{FAULT}": "AMP_FAULT",
             "OUT_A+": "OUTA_P", "OUT_A-": "OUTA_N", "OUT_B+": "OUTB_P", "OUT_B-": "OUTB_N",
             "BST_A+": "BSTA_P", "BST_A-": "BSTA_N", "BST_B+": "BSTB_P", "BST_B-": "BSTB_N",
         }, nc=("SDOUT",)),
    Part("C7", "220u 25V", "Device:C_Polarized", "Capacitor_SMD:CP_Elec_6.3x7.7", (163.0, 107.5), group="Audio",
         nets={"1": "VSYS", "2": "GND"}),
    C("C8", "10u 25V", "VSYS", "GND", (172.0, 113.0), "1206", group="Audio"),
    C("C9", "10u 25V", "VSYS", "GND", (172.0, 133.0), "1206", group="Audio"),
    C("C10", "100n", "+3V3", "GND", (158.0, 117.0), group="Audio"),
    C("C11", "1u", "AMP_AVDD", "GND", (158.0, 121.0), group="Audio"),
    C("C12", "1u", "AMP_VRDIG", "GND", (158.0, 125.0), group="Audio"),
    C("C13", "220n", "BSTA_P", "OUTA_P", (172.0, 118.5), group="Audio"),
    C("C14", "220n", "BSTA_N", "OUTA_N", (172.0, 121.5), group="Audio"),
    C("C15", "220n", "BSTB_P", "OUTB_P", (172.0, 124.5), group="Audio"),
    C("C16", "220n", "BSTB_N", "OUTB_N", (172.0, 127.5), group="Audio"),
    Part("FB1", "120R@100MHz 4A", "Device:FerriteBead", "Inductor_SMD:L_1206_3216Metric", (178.0, 116.0), group="Audio",
         nets={"1": "OUTA_P", "2": "SPK_R_P"}),
    Part("FB2", "120R@100MHz 4A", "Device:FerriteBead", "Inductor_SMD:L_1206_3216Metric", (178.0, 120.0), group="Audio",
         nets={"1": "OUTA_N", "2": "SPK_R_N"}),
    Part("FB3", "120R@100MHz 4A", "Device:FerriteBead", "Inductor_SMD:L_1206_3216Metric", (178.0, 126.0), group="Audio",
         nets={"1": "OUTB_P", "2": "SPK_L_P"}),
    Part("FB4", "120R@100MHz 4A", "Device:FerriteBead", "Inductor_SMD:L_1206_3216Metric", (178.0, 130.0), group="Audio",
         nets={"1": "OUTB_N", "2": "SPK_L_N"}),
    C("C17", "1n", "SPK_R_P", "GND", (183.0, 116.0), group="Audio"),
    C("C18", "1n", "SPK_R_N", "GND", (183.0, 120.0), group="Audio"),
    C("C19", "1n", "SPK_L_P", "GND", (183.0, 126.0), group="Audio"),
    C("C20", "1n", "SPK_L_N", "GND", (183.0, 130.0), group="Audio"),
    Part("J4", "SPK_R", "Connector_Generic:Conn_01x02", "Connector_JST:JST_PH_B2B-PH-K_1x02_P2.00mm_Vertical",
         (140.0, 104.5), group="Audio", nets={"1": "SPK_R_P", "2": "SPK_R_N"}),
    Part("J5", "SPK_L", "Connector_Generic:Conn_01x02", "Connector_JST:JST_PH_B2B-PH-K_1x02_P2.00mm_Vertical",
         (280.0, 104.5), group="Audio", nets={"1": "SPK_L_P", "2": "SPK_L_N"}),

    # ------------------------------------------------------------ Charger
    Part("U3", "BQ25792RQMR", "Battery_Management:BQ25798", "Package_DFN_QFN:Texas_RQM0029A_VQFN-29_4x4mm_P0.4mm",
         (290.0, 121.0), group="Power", nets={
             "VBUS": "VBUS", "VAC1": "VBUS", "VAC2": "GND", "PMID": "CHG_PMID", "REGN": "CHG_REGN",
             "BTST1": "CHG_BTST1", "SW1": "CHG_SW1", "SW2": "CHG_SW2", "BTST2": "CHG_BTST2",
             "SYS": "VSYS", "BAT": "VBAT", "BATP": "VBAT", "GND": "GND",
             "SDA": "I2C_SDA", "SCL": "I2C_SCL", "~{INT}": "CHG_INT", "~{CE}": "GND",
             "TS": "CHG_TS", "ILIM_HIZ": "CHG_ILIM", "PROG": "CHG_PROG",
         }, nc=("STAT", "D+", "D-", "ACDRV1", "ACDRV2", "~{QON}", "SDRV")),
    Part("L1", "1u XAL6030", "Device:L", "Inductor_SMD:L_Coilcraft_XAL6030-XXX", (303.0, 112.0), group="Power",
         nets={"1": "CHG_SW1", "2": "CHG_SW2"}),
    C("C21", "10u 25V", "VBUS", "GND", (276.0, 116.0), "1206", group="Power"),
    C("C22", "10u 25V", "CHG_PMID", "GND", (282.0, 116.0), "1206", rot=90, group="Power"),
    C("C23", "47n", "CHG_BTST1", "CHG_SW1", (296.0, 117.0), group="Power"),
    C("C24", "47n", "CHG_BTST2", "CHG_SW2", (296.0, 120.0), group="Power"),
    C("C25", "4u7", "CHG_REGN", "GND", (284.0, 125.0), group="Power"),
    C("C26", "22u 25V", "VSYS", "GND", (297.0, 128.0), "1206", group="Power"),
    C("C27", "22u 25V", "VSYS", "GND", (302.5, 128.0), "1206", group="Power"),
    C("C28", "10u 25V", "VBAT", "GND", (310.0, 128.0), "1206", group="Power"),
    R("R5", "PROG 3S", "CHG_PROG", "GND", (284.0, 128.0), group="Power"),
    R("R6", "ILIM", "CHG_ILIM", "GND", (284.0, 131.0), group="Power"),
    R("R7", "5k23", "CHG_REGN", "CHG_TS", (289.0, 131.0), group="Power"),
    R("R8", "30k1", "CHG_TS", "GND", (293.0, 131.0), group="Power"),
    Part("J3", "BATTERY 3S", "Connector_Generic:Conn_01x03", "Connector_JST:JST_XH_B3B-XH-A_1x03_P2.50mm_Vertical",
         (311.5, 104.5), group="Power", nets={"1": "VBAT", "2": "GND", "3": "CHG_TS"}),
    Part("J1", "USB LEAD", "Connector_Generic:Conn_01x06", "Connector_JST:JST_PH_B6B-PH-K_1x06_P2.00mm_Vertical",
         (207.0, 104.5), group="Power", nets={"1": "VBUS", "2": "VBUS", "3": "GND", "4": "GND",
                                                       "5": "USB_DP", "6": "USB_DN"}),

    # ------------------------------------------------------------ 3.3 V buck
    Part("U4", "TPS62933DRLR", "Regulator_Switching:TPS62933", "Package_TO_SOT_SMD:SOT-583-8", (265.0, 136.0),
         group="Power", nets={"VIN": "VSYS", "GND": "GND", "EN": "BUCK_EN", "SW": "BUCK_SW", "BST": "BUCK_BST",
                              "FB": "BUCK_FB", "SS": "BUCK_SS"}, nc=("RT",)),
    Part("L2", "4u7 XAL4030", "Device:L", "Inductor_SMD:L_Coilcraft_XAL4030-XXX", (272.5, 136.0), group="Power",
         nets={"1": "BUCK_SW", "2": "+3V3"}),
    C("C29", "10u 25V", "VSYS", "GND", (258.0, 136.0), "1206", rot=90, group="Power"),
    C("C30", "100n", "BUCK_BST", "BUCK_SW", (265.0, 140.5), group="Power"),
    C("C31", "22u", "+3V3", "GND", (279.0, 134.0), "0805", group="Power"),
    C("C32", "22u", "+3V3", "GND", (279.0, 137.5), "0805", group="Power"),
    C("C33", "10n", "BUCK_SS", "GND", (270.0, 141.5), group="Power"),
    R("R9", "100k", "VSYS", "BUCK_EN", (261.0, 131.0), group="Power"),
    R("R10", "100k", "+3V3", "BUCK_FB", (265.0, 131.0), group="Power"),
    R("R11", "31k6", "BUCK_FB", "GND", (269.0, 131.0), group="Power"),

    # ------------------------------------------------------------ User interface
    Part("SW1", "PREV", "Switch:SW_Push", "Button_Switch_THT:SW_PUSH_6mm_H5mm", from_cad(-18, 30), side="bottom",
         group="UI", nets={"1": "KEY_PREV", "2": "GND"}),
    Part("SW2", "PLAY", "Switch:SW_Push", "Button_Switch_THT:SW_PUSH_6mm_H5mm", from_cad(0, 30), side="bottom",
         group="UI", nets={"1": "KEY_PLAY", "2": "GND"}),
    Part("SW3", "NEXT", "Switch:SW_Push", "Button_Switch_THT:SW_PUSH_6mm_H5mm", from_cad(18, 30), side="bottom",
         group="UI", nets={"1": "KEY_NEXT", "2": "GND"}),
    Part("J2", "LCD", "Connector_Generic:Conn_01x12", "Connector_FFC-FPC:Hirose_FH12-12S-0.5SH_1x12-1MP_P0.50mm_Horizontal",
         from_cad(-57, 30), rot=90, side="bottom", group="UI", nets={
             "1": "+3V3", "2": "GND", "3": "LCD_SCK", "4": "LCD_MOSI", "5": "LCD_CS", "6": "LCD_DC",
             "7": "LCD_RST", "8": "LCD_BL", "9": "I2C_SDA", "10": "I2C_SCL", "11": "TP_INT", "12": "TP_RST"}),
    Part("J6", "ENCODER", "Connector_Generic:Conn_01x05", "Connector_JST:JST_PH_B5B-PH-K_1x05_P2.00mm_Vertical",
         (120.0, 104.5), group="UI", nets={"1": "ENC_A", "2": "ENC_B", "3": "GND", "4": "ENC_SW", "5": "GND"}),

    # ------------------------------------------------------------ Mounting holes (enclosure bosses)
    *[Part(f"H{i + 1}", "M3", "Mechanical:MountingHole_Pad", "MountingHole:MountingHole_3.2mm_M3_Pad", from_cad(x, 30 + z),
           group="Mechanical", nets={"1": "GND"})
      for i, (x, z) in enumerate([(-32, -18), (-32, 18), (60, -18), (60, 18)])],
]

# Nets that need a PWR_FLAG: no power output pin drives them on this board.
POWER_FLAGS = ["GND", "+3V3", "VBUS"]
