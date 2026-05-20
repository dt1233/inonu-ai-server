#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PDF metin kalite raporu - Türkçe karakter doğrulama"""

import json

with open("data/crawl_results.json", "r", encoding="utf-8") as f:
    data = json.load(f)

report_lines = []
turkish_chars = set("ıİğĞüÜöÖşŞçÇ")

total_att = 0
success_att = 0
broken_att = 0
empty_att = 0

broken_examples = []
success_examples = []

for ann in data.get("announcements", []):
    ann_id = ann.get("id", "?")
    for att in ann.get("attachments", []):
        if att.get("type") == "pdf":
            total_att += 1
            content = att.get("content", "")
            if content == "[PDF Okunamadı]" or not content.strip():
                empty_att += 1
            elif any(c in turkish_chars for c in content):
                success_att += 1
                if len(success_examples) < 5:
                    success_examples.append((ann_id, content[:300]))
            else:
                broken_att += 1
                if len(broken_examples) < 10:
                    broken_examples.append((ann_id, content[:300]))

report_lines.append("=" * 60)
report_lines.append("PDF METİN KALİTE RAPORU")
report_lines.append("=" * 60)
report_lines.append(f"Toplam PDF eki: {total_att}")
report_lines.append(f"Türkçe karakter içeren (sağlam): {success_att}")
report_lines.append(f"Türkçe karakter İÇERMEYEN (potansiyel bozuk): {broken_att}")
report_lines.append(f"Okunamayan/Boş ([PDF Okunamadı]): {empty_att}")
report_lines.append("")

report_lines.append("=" * 60)
report_lines.append("SAĞLAM PDF ÖRNEKLERİ (Türkçe karakterler doğru)")
report_lines.append("=" * 60)
for ann_id, text in success_examples:
    report_lines.append(f"--- Duyuru ID: {ann_id} ---")
    report_lines.append(text)
    report_lines.append("")

report_lines.append("=" * 60)
report_lines.append("BOZUK OLABİLECEK PDF ÖRNEKLERİ (Türkçe karakter yok)")
report_lines.append("=" * 60)
for ann_id, text in broken_examples:
    report_lines.append(f"--- Duyuru ID: {ann_id} ---")
    report_lines.append(text)
    report_lines.append("")

with open("data/pdf_kalite_raporu.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(report_lines))

print("Rapor yazildi: data/pdf_kalite_raporu.txt")
