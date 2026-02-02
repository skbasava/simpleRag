import xml.etree.ElementTree as ET

def parse_mpu(xml_text, target_mpu):
    """
    Parse only ONE MPU.
    Avoids full XML expansion.
    """
    root = ET.fromstring(xml_text)

    for mpu in root.findall(".//MPU"):
        if mpu.attrib.get("name") != target_mpu:
            continue

        regions = []
        for region in mpu.findall(".//Region"):
            regions.append(
                ET.tostring(region, encoding="unicode")
            )

        return regions

    return None