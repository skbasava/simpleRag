from typing import List, Dict
import xml.etree.ElementTree as ET
from pathlib import Path


def parse_xml_into_chunks(
    xml_path: str,
    project: str,
) -> List[Dict]:
    """
    Parse MPU XML into PolicyChunkRecord dicts
    aligned with policy_chunks schema.
    """

    tree = ET.parse(xml_path)
    root = tree.getroot()

    chunks: List[Dict] = []
    chunk_index = 0

    for mpu in root.findall(".//MPU"):
        mpu_name = mpu.attrib.get("name") or mpu.attrib.get("fqname")

        for prtn in mpu.findall(".//PRTn"):
            rg_index = int(prtn.attrib["index"])
            profile = prtn.attrib["profile"]

            start_hex = prtn.attrib["start"]
            end_hex = prtn.attrib["end"]

            start_dec = hex_to_dec(start_hex)
            end_dec = hex_to_dec(end_hex)

            rdomains = prtn.attrib.get("rdomains", "").split(",")
            wdomains = prtn.attrib.get("wdomains", "").split(",")

            rdomains = [d for d in rdomains if d]
            wdomains = [d for d in wdomains if d]

            # ---- text extraction ----
            rationale = prtn.findtext("SecurityRationale", default="")
            poc = prtn.findtext("SecurityRationalePoC", default="")

            chunk_text = "\n".join(
                line.strip()
                for line in [rationale, poc]
                if line.strip()
            )

            # ---- identity & content hashes ----
            identity_key = f"{project}|{mpu_name}|{rg_index}|{profile}|{start_hex}|{end_hex}"
            identity_hash = sha256(identity_key)

            content_hash = sha256(chunk_text)

            chunks.append({
                "project": project,
                "mpu_name": mpu_name,
                "rg_index": rg_index,
                "profile": profile,

                "start_hex": start_hex,
                "end_hex": end_hex,
                "start_dec": start_dec,
                "end_dec": end_dec,

                "rdomains": rdomains,
                "wdomains": wdomains,

                "chunk_index": chunk_index,
                "chunk_text": chunk_text,

                "identity_hash": identity_hash,
                "content_hash": content_hash,

                "vector_id": None,
                "is_active": True,
            })

            chunk_index += 1

    return chunks