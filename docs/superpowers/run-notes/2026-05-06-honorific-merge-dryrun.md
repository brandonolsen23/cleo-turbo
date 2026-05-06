# Honorific Merge — Dry Run Report

- DB: `data/cleo.db`
- Generated: 2026-05-06
- Total contacts: 83,883
- New-fingerprint groups with >=2 contacts: **77**
- Total losers (will redirect + delete): **77**
- Singletons whose fingerprint just changes (no merge): **132**

### Suspicious cases (no shared phone AND no shared group): **39**
These should be reviewed extra carefully — there's no signal that they're the same person beyond the name.

## Proposed merges

| New fingerprint | Winner (CON_ID · name · txns) | Losers (CON_ID · name · txns) | Shared phone? | Shared group? | Tiebreaker |
|---|---|---|---|---|---|
| `JENNIFER ADAMS` | CON_00435 · Jennifer Adams · txns:4 | CON_11270 · Dr Jennifer Adams · txns:2 | yes | yes | canonical-already-clean |
| `MAX BLOUW` | CON_04118 · Max Blouw · txns:5 | CON_00492 · Dr Max Blouw · txns:2 | yes | yes | canonical-already-clean |
| `SHEETAL SAPRA` | CON_00776 · Sheetal Sapra · txns:2 | CON_83593 · Dr Sheetal Sapra · txns:1 | no | no | canonical-already-clean |
| `THARWAT FERA` | CON_82427 · Tharwat Fera · txns:1 | CON_02916 · Dr Tharwat Fera · txns:1 | no | no | canonical-already-clean |
| `B. ABROMEIT-KREMSER` | CON_03520 · B. Abromeit-Kremser · txns:13 | CON_33623 · Dr B. Abromeit-Kremser · txns:1 | no | no | canonical-already-clean |
| `PAUL IVANY` | CON_68447 · Paul Ivany · txns:3 | CON_04571 · Rev Paul Ivany · txns:1 | no | no | canonical-already-clean |
| `ALLEN GREENSPOON` | CON_05590 · Allen Greenspoon · txns:4 | CON_73154 · Dr Allen Greenspoon · txns:1 | no | no | canonical-already-clean |
| `ORAL OKEM` | CON_07068 · Oral Okem · txns:3 | CON_75506 · Dr Oral Okem · txns:1 | no | yes | canonical-already-clean |
| `ROBERT WONG` | CON_07204 · Robert Wong · txns:2 | CON_09839 · Rev Robert Wong · txns:1 | no | no | canonical-already-clean |
| `ADAM MOHAMMED` | CON_24301 · Adam Mohammed · txns:2 | CON_07443 · Dr Adam Mohammed · txns:1 | no | yes | canonical-already-clean |
| `GREGORY HANAKA` | CON_63304 · Gregory Hanaka · txns:1 | CON_07604 · Dr Gregory Hanaka · txns:1 | no | yes | canonical-already-clean |
| `BHAN GARG` | CON_07925 · Bhan Garg · txns:17 | CON_25540 · Dr Bhan Garg · txns:1 | no | no | canonical-already-clean |
| `KEVIN SMITH` | CON_08360 · Kevin Smith · txns:7 | CON_81905 · Dr Kevin Smith · txns:1 | no | no | canonical-already-clean |
| `BIJAN PARDIS` | CON_08406 · Bijan Pardis · txns:9 | CON_57963 · Dr Bijan Pardis · txns:1 | yes | no | canonical-already-clean |
| `MOHAMAD SALAME` | CON_35113 · Mohamad Salame · txns:1 | CON_09599 · Dr Mohamad Salame · txns:1 | no | yes | canonical-already-clean |
| `ATHANASIUS ISKANDER` | CON_10304 · Athanasius Iskander · txns:1 | CON_61834 · Father Athanasius Iskander · txns:1 | yes | no | canonical-already-clean |
| `WILLIAM JAMES` | CON_10574 · William James · txns:3 | CON_79657 · Dr William James · txns:1 | no | no | canonical-already-clean |
| `MICHAEL SHIH` | CON_11054 · Michael Shih · txns:14 | CON_75924 · Dr Michael Shih · txns:1 | yes | no | canonical-already-clean |
| `CHANG WANG` | CON_11437 · Chang Wang · txns:3 | CON_72538 · Dr Chang Wang · txns:1 | no | no | canonical-already-clean |
| `WALLACE WHISTANCE-SMITH` | CON_67462 · Wallace Whistance-Smith · txns:2 | CON_14674 · Dr Wallace Whistance-Smith · txns:1 | no | yes | canonical-already-clean |
| `DOUGLAS WIEBE` | CON_15042 · Douglas Wiebe · txns:1 | CON_56441 · Rev Douglas Wiebe · txns:1 | no | no | canonical-already-clean |
| `MAHENDRA JAIN` | CON_15097 · Mahendra Jain · txns:6 | CON_57723 · Dr Mahendra Jain · txns:1 | no | no | canonical-already-clean |
| `HAGOP BOYRAZIAN` | CON_15227 · Hagop Boyrazian · txns:3 | CON_21394 · Dr. Hagop Boyrazian · txns:1 | no | no | canonical-already-clean |
| `ELBERT MURRELL` | CON_15747 · Elbert Murrell · txns:11 | CON_15371 · Dr Elbert Murrell · txns:1 | no | no | canonical-already-clean |
| `OSCAR DALMAO` | CON_64378 · Oscar Dalmao · txns:2 | CON_15852 · Dr Oscar Dalmao · txns:1 | no | yes | canonical-already-clean |
| `JOSEPH WONG` | CON_16531 · Joseph Wong · txns:2 | CON_29172 · Dr Joseph Wong · txns:1 | no | no | canonical-already-clean |
| `HARINDER SAINI` | CON_16798 · Harinder Saini · txns:1 | CON_26626 · Dr Harinder Saini · txns:1 | no | yes | canonical-already-clean |
| `RAPHAEL JANKOWSKI` | CON_17015 · Raphael Jankowski · txns:2 | CON_21371 · Dr Raphael Jankowski · txns:1 | no | no | canonical-already-clean |
| `HARRY ARONOWICZ` | CON_17413 · Harry Aronowicz · txns:3 | CON_25005 · Dr Harry Aronowicz · txns:2 | yes | yes | canonical-already-clean |
| `RICHARD BLUM` | CON_17850 · Richard Blum · txns:1 | CON_80142 · Dr Richard Blum · txns:1 | no | no | canonical-already-clean |
| `MOHAMED TABIB` | CON_18502 · Mohamed Tabib · txns:8 | CON_18392 · Dr Mohamed Tabib · txns:1 | no | no | canonical-already-clean |
| `JAMES MACLEAN` | CON_18409 · James MacLean · txns:2 | CON_55368 · Dr James Maclean · txns:1 | no | no | canonical-already-clean |
| `AMANDA LEPP` | CON_18578 · Amanda Lepp · txns:1 | CON_32831 · Dr Amanda Lepp · txns:1 | no | no | canonical-already-clean |
| `MARK FOULLONG` | CON_19178 · Mark Foullong · txns:2 | CON_67318 · Dr Mark Foullong · txns:1 | no | no | canonical-already-clean |
| `RICHARD TYTUS` | CON_19248 · Richard Tytus · txns:3 | CON_19521 · Dr Richard Tytus · txns:1 | no | yes | canonical-already-clean |
| `BERND ABROMEIT-KREMSER` | CON_20504 · Bernd Abromeit-Kremser · txns:1 | CON_21715 · Dr. Bernd Abromeit-Kremser · txns:2 | no | no | canonical-already-clean |
| `STEVEN MASCARIN` | CON_75342 · Steven Mascarin · txns:2 | CON_20708 · Dr Steven Mascarin · txns:1 | no | no | canonical-already-clean |
| `LLOYD WEBER` | CON_20935 · Lloyd Weber · txns:3 | CON_50468 · Dr. Lloyd Weber · txns:1 | no | yes | canonical-already-clean |
| `LINDA GRAYSON` | CON_22231 · Linda Grayson · txns:6 | CON_59918 · Dr Linda Grayson · txns:1 | yes | yes | canonical-already-clean |
| `AHMED SEKSEK` | CON_26457 · Ahmed Seksek · txns:6 | CON_22575 · Dr Ahmed Seksek · txns:2 | no | no | canonical-already-clean |
| `DANIEL MACDONALD` | CON_23498 · Daniel MacDonald · txns:1 | CON_71074 · Rev Daniel MacDonald · txns:1 | no | no | canonical-already-clean |
| `KABIR JIVRAJ` | CON_67549 · Kabir Jivraj · txns:1 | CON_23988 · Dr Kabir Jivraj · txns:1 | no | no | canonical-already-clean |
| `CONOR TURLEY` | CON_67397 · Conor Turley · txns:1 | CON_24030 · Dr Conor Turley · txns:2 | no | yes | canonical-already-clean |
| `ARTAJ SINGH` | CON_24351 · Artaj Singh · txns:1 | CON_57553 · Dr Artaj Singh · txns:1 | no | yes | canonical-already-clean |
| `ROLAND SABBAGH` | CON_27473 · Roland Sabbagh · txns:2 | CON_32063 · Dr. Roland Sabbagh · txns:1 | yes | yes | canonical-already-clean |
| `GERVAN FEARON` | CON_28937 · Gervan Fearon · txns:1 | CON_43016 · Dr Gervan Fearon · txns:1 | no | no | canonical-already-clean |
| `MARK NUSBAUM` | CON_28989 · Mark Nusbaum · txns:2 | CON_77691 · Dr Mark Nusbaum · txns:1 | yes | no | canonical-already-clean |
| `CHARLES GARDNER` | CON_32647 · Charles Gardner · txns:1 | CON_69727 · Dr Charles Gardner · txns:1 | no | no | canonical-already-clean |
| `IRVING ESSER` | CON_34945 · Irving Esser · txns:2 | CON_56067 · Dr Irving Esser · txns:1 | no | yes | canonical-already-clean |
| `P. SUGANDAN` | CON_36275 · P. Sugandan · txns:2 | CON_80015 · Dr P. Sugandan · txns:1 | no | no | canonical-already-clean |
| `ASLAM DAUD` | CON_44207 · Aslam Daud · txns:1 | CON_36614 · Dr Aslam Daud · txns:1 | yes | yes | canonical-already-clean |
| `ROSS PAUL` | CON_38189 · Ross Paul · txns:1 | CON_59763 · Dr Ross Paul · txns:1 | no | yes | canonical-already-clean |
| `DONALD REIMER` | CON_38391 · Donald Reimer · txns:1 | CON_60198 · Dr Donald Reimer · txns:1 | no | no | canonical-already-clean |
| `YANG LIU` | CON_45216 · Yang Liu · txns:2 | CON_39749 · Dr Yang Liu · txns:1 | no | no | canonical-already-clean |
| `MOUNIR AZER` | CON_40838 · Mounir Azer · txns:1 | CON_81784 · Dr Mounir Azer · txns:1 | no | no | canonical-already-clean |
| `FAYSAL NAJI` | CON_42569 · Faysal Naji · txns:1 | CON_49236 · Dr Faysal Naji · txns:1 | no | yes | canonical-already-clean |
| `NIAZ TOMA` | CON_47973 · Niaz Toma · txns:1 | CON_82112 · Rev Niaz Toma · txns:1 | no | yes | canonical-already-clean |
| `ROBERT CHEVRIER` | CON_48814 · Robert Chevrier · txns:6 | CON_82312 · Dr. Robert Chevrier · txns:1 | no | no | canonical-already-clean |
| `EUGENE JURGUTIS` | CON_49673 · Eugene Jurgutis · txns:1 | CON_50019 · Rev Eugene Jurgutis · txns:1 | no | no | canonical-already-clean |
| `PETER NOBILI` | CON_50400 · Rev Peter Nobili · txns:1 | CON_58898 · Rev. Peter Nobili · txns:1 | yes | no | lowest-CON_ID (no canonical) |
| `MURRAY FRUM` | CON_52612 · Murray Frum · txns:3 | CON_51445 · Dr Murray Frum · txns:6 | yes | no | canonical-already-clean |
| `WING LEE` | CON_64205 · Wing Lee · txns:2 | CON_51728 · Rev Wing Lee · txns:1 | no | no | canonical-already-clean |
| `ANGELOS SAAD` | CON_51740 · Father Angelos Saad · txns:7 | CON_79818 · Fr Angelos Saad · txns:1 | yes | no | lowest-CON_ID (no canonical) |
| `SAMUEL LAM` | CON_51811 · Samuel Lam · txns:5 | CON_57004 · Dr Samuel Lam · txns:1 | no | no | canonical-already-clean |
| `ENZO DIANA` | CON_53249 · Enzo Diana · txns:1 | CON_54400 · Dr. Enzo Diana · txns:1 | no | yes | canonical-already-clean |
| `GEORGE CORMACK` | CON_54197 · George Cormack · txns:3 | CON_67983 · Dr George Cormack · txns:1 | no | yes | canonical-already-clean |
| `JOHN MCKENZIE` | CON_55260 · John McKenzie · txns:1 | CON_63884 · Dr John McKenzie · txns:1 | no | no | canonical-already-clean |
| `EDDIE LO` | CON_57780 · Eddie Lo · txns:1 | CON_82906 · Dr Eddie Lo · txns:1 | no | no | canonical-already-clean |
| `LORNE RACHLIS` | CON_61547 · Lorne Rachlis · txns:2 | CON_61231 · Dr Lorne Rachlis · txns:3 | yes | no | canonical-already-clean |
| `EVTIMY WOLINSKI` | CON_81321 · Evtimy Wolinski · txns:1 | CON_62882 · Rev. Evtimy Wolinski · txns:1 | no | yes | canonical-already-clean |
| `WINSTON RYE` | CON_64050 · Rev Winston Rye · txns:1 | CON_69466 · Rev. Winston Rye · txns:1 | yes | no | lowest-CON_ID (no canonical) |
| `HARRY PARROTT` | CON_64467 · Harry Parrott · txns:2 | CON_67250 · Dr Harry Parrott · txns:1 | no | yes | canonical-already-clean |
| `ANAND AGGERWAL` | CON_65082 · Anand Aggerwal · txns:1 | CON_67151 · Dr Anand Aggerwal · txns:1 | no | yes | canonical-already-clean |
| `EUGENE RICHLARK` | CON_66558 · Rev. Eugene Richlark · txns:1 | CON_69677 · Rev Eugene Richlark · txns:1 | no | yes | lowest-CON_ID (no canonical) |
| `MOONA RAHEMTULLA` | CON_79791 · Moona Rahemtulla · txns:1 | CON_69942 · Dr Moona Rahemtulla · txns:1 | no | no | canonical-already-clean |
| `CARMEN LEWIS` | CON_73803 · Carmen Lewis · txns:1 | CON_73842 · Dr Carmen Lewis · txns:1 | no | yes | canonical-already-clean |
| `ABOOBAKER ABOO` | CON_78806 · Aboobaker Aboo · txns:1 | CON_80708 · Dr Aboobaker Aboo · txns:1 | yes | no | canonical-already-clean |

## Per-merge CRM data counts

Counts for tables that would be redirected (so you can see if the survivor inherits everything correctly).
Format: `txn_parties / notes / activities / stars / list_memb / group_links / buy_mand / overrides / work_hist`

### `JENNIFER ADAMS`

- **Winner** CON_00435 (Jennifer Adams): 4 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Loser   CON_11270 (Dr Jennifer Adams): 2 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Shared groups: GRP_00507

### `MAX BLOUW`

- **Winner** CON_04118 (Max Blouw): 5 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Loser   CON_00492 (Dr Max Blouw): 2 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Shared groups: GRP_00572

### `SHEETAL SAPRA`

- **Winner** CON_00776 (Sheetal Sapra): 2 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Loser   CON_83593 (Dr Sheetal Sapra): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0

### `THARWAT FERA`

- **Winner** CON_82427 (Tharwat Fera): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Loser   CON_02916 (Dr Tharwat Fera): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0

### `B. ABROMEIT-KREMSER`

- **Winner** CON_03520 (B. Abromeit-Kremser): 13 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Loser   CON_33623 (Dr B. Abromeit-Kremser): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0

### `PAUL IVANY`

- **Winner** CON_68447 (Paul Ivany): 3 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Loser   CON_04571 (Rev Paul Ivany): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0

### `ALLEN GREENSPOON`

- **Winner** CON_05590 (Allen Greenspoon): 4 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Loser   CON_73154 (Dr Allen Greenspoon): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0

### `ORAL OKEM`

- **Winner** CON_07068 (Oral Okem): 3 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Loser   CON_75506 (Dr Oral Okem): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Shared groups: GRP_08739

### `ROBERT WONG`

- **Winner** CON_07204 (Robert Wong): 2 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Loser   CON_09839 (Rev Robert Wong): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0

### `ADAM MOHAMMED`

- **Winner** CON_24301 (Adam Mohammed): 2 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Loser   CON_07443 (Dr Adam Mohammed): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Shared groups: GRP_09194

### `GREGORY HANAKA`

- **Winner** CON_63304 (Gregory Hanaka): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Loser   CON_07604 (Dr Gregory Hanaka): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Shared groups: GRP_09402

### `BHAN GARG`

- **Winner** CON_07925 (Bhan Garg): 17 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Loser   CON_25540 (Dr Bhan Garg): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0

### `KEVIN SMITH`

- **Winner** CON_08360 (Kevin Smith): 7 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Loser   CON_81905 (Dr Kevin Smith): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0

### `BIJAN PARDIS`

- **Winner** CON_08406 (Bijan Pardis): 9 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Loser   CON_57963 (Dr Bijan Pardis): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0

### `MOHAMAD SALAME`

- **Winner** CON_35113 (Mohamad Salame): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Loser   CON_09599 (Dr Mohamad Salame): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Shared groups: GRP_12068

### `ATHANASIUS ISKANDER`

- **Winner** CON_10304 (Athanasius Iskander): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Loser   CON_61834 (Father Athanasius Iskander): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0

### `WILLIAM JAMES`

- **Winner** CON_10574 (William James): 3 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Loser   CON_79657 (Dr William James): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0

### `MICHAEL SHIH`

- **Winner** CON_11054 (Michael Shih): 14 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Loser   CON_75924 (Dr Michael Shih): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0

### `CHANG WANG`

- **Winner** CON_11437 (Chang Wang): 3 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Loser   CON_72538 (Dr Chang Wang): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0

### `WALLACE WHISTANCE-SMITH`

- **Winner** CON_67462 (Wallace Whistance-Smith): 2 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Loser   CON_14674 (Dr Wallace Whistance-Smith): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Shared groups: GRP_18884

### `DOUGLAS WIEBE`

- **Winner** CON_15042 (Douglas Wiebe): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Loser   CON_56441 (Rev Douglas Wiebe): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0

### `MAHENDRA JAIN`

- **Winner** CON_15097 (Mahendra Jain): 6 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Loser   CON_57723 (Dr Mahendra Jain): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0

### `HAGOP BOYRAZIAN`

- **Winner** CON_15227 (Hagop Boyrazian): 3 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Loser   CON_21394 (Dr. Hagop Boyrazian): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0

### `ELBERT MURRELL`

- **Winner** CON_15747 (Elbert Murrell): 11 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Loser   CON_15371 (Dr Elbert Murrell): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0

### `OSCAR DALMAO`

- **Winner** CON_64378 (Oscar Dalmao): 2 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Loser   CON_15852 (Dr Oscar Dalmao): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Shared groups: GRP_20529

### `JOSEPH WONG`

- **Winner** CON_16531 (Joseph Wong): 2 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Loser   CON_29172 (Dr Joseph Wong): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0

### `HARINDER SAINI`

- **Winner** CON_16798 (Harinder Saini): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Loser   CON_26626 (Dr Harinder Saini): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Shared groups: GRP_21857

### `RAPHAEL JANKOWSKI`

- **Winner** CON_17015 (Raphael Jankowski): 2 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Loser   CON_21371 (Dr Raphael Jankowski): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0

### `HARRY ARONOWICZ`

- **Winner** CON_17413 (Harry Aronowicz): 3 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Loser   CON_25005 (Dr Harry Aronowicz): 2 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Shared groups: GRP_22771

### `RICHARD BLUM`

- **Winner** CON_17850 (Richard Blum): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Loser   CON_80142 (Dr Richard Blum): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0

### `MOHAMED TABIB`

- **Winner** CON_18502 (Mohamed Tabib): 8 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Loser   CON_18392 (Dr Mohamed Tabib): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0

### `JAMES MACLEAN`

- **Winner** CON_18409 (James MacLean): 2 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Loser   CON_55368 (Dr James Maclean): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0

### `AMANDA LEPP`

- **Winner** CON_18578 (Amanda Lepp): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Loser   CON_32831 (Dr Amanda Lepp): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0

### `MARK FOULLONG`

- **Winner** CON_19178 (Mark Foullong): 2 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Loser   CON_67318 (Dr Mark Foullong): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0

### `RICHARD TYTUS`

- **Winner** CON_19248 (Richard Tytus): 3 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Loser   CON_19521 (Dr Richard Tytus): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Shared groups: GRP_25717

### `BERND ABROMEIT-KREMSER`

- **Winner** CON_20504 (Bernd Abromeit-Kremser): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Loser   CON_21715 (Dr. Bernd Abromeit-Kremser): 2 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0

### `STEVEN MASCARIN`

- **Winner** CON_75342 (Steven Mascarin): 2 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Loser   CON_20708 (Dr Steven Mascarin): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0

### `LLOYD WEBER`

- **Winner** CON_20935 (Lloyd Weber): 3 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Loser   CON_50468 (Dr. Lloyd Weber): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Shared groups: GRP_27749

### `LINDA GRAYSON`

- **Winner** CON_22231 (Linda Grayson): 6 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Loser   CON_59918 (Dr Linda Grayson): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Shared groups: GRP_99216

### `AHMED SEKSEK`

- **Winner** CON_26457 (Ahmed Seksek): 6 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Loser   CON_22575 (Dr Ahmed Seksek): 2 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0

### `DANIEL MACDONALD`

- **Winner** CON_23498 (Daniel MacDonald): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Loser   CON_71074 (Rev Daniel MacDonald): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0

### `KABIR JIVRAJ`

- **Winner** CON_67549 (Kabir Jivraj): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Loser   CON_23988 (Dr Kabir Jivraj): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0

### `CONOR TURLEY`

- **Winner** CON_67397 (Conor Turley): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Loser   CON_24030 (Dr Conor Turley): 2 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Shared groups: GRP_32248

### `ARTAJ SINGH`

- **Winner** CON_24351 (Artaj Singh): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Loser   CON_57553 (Dr Artaj Singh): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Shared groups: GRP_32701

### `ROLAND SABBAGH`

- **Winner** CON_27473 (Roland Sabbagh): 2 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Loser   CON_32063 (Dr. Roland Sabbagh): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Shared groups: GRP_37333

### `GERVAN FEARON`

- **Winner** CON_28937 (Gervan Fearon): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Loser   CON_43016 (Dr Gervan Fearon): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0

### `MARK NUSBAUM`

- **Winner** CON_28989 (Mark Nusbaum): 2 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Loser   CON_77691 (Dr Mark Nusbaum): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0

### `CHARLES GARDNER`

- **Winner** CON_32647 (Charles Gardner): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Loser   CON_69727 (Dr Charles Gardner): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0

### `IRVING ESSER`

- **Winner** CON_34945 (Irving Esser): 2 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Loser   CON_56067 (Dr Irving Esser): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Shared groups: GRP_93570

### `P. SUGANDAN`

- **Winner** CON_36275 (P. Sugandan): 2 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Loser   CON_80015 (Dr P. Sugandan): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0

### `ASLAM DAUD`

- **Winner** CON_44207 (Aslam Daud): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Loser   CON_36614 (Dr Aslam Daud): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Shared groups: GRP_53926

### `ROSS PAUL`

- **Winner** CON_38189 (Ross Paul): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Loser   CON_59763 (Dr Ross Paul): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Shared groups: GRP_00825

### `DONALD REIMER`

- **Winner** CON_38391 (Donald Reimer): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Loser   CON_60198 (Dr Donald Reimer): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0

### `YANG LIU`

- **Winner** CON_45216 (Yang Liu): 2 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Loser   CON_39749 (Dr Yang Liu): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0

### `MOUNIR AZER`

- **Winner** CON_40838 (Mounir Azer): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Loser   CON_81784 (Dr Mounir Azer): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0

### `FAYSAL NAJI`

- **Winner** CON_42569 (Faysal Naji): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Loser   CON_49236 (Dr Faysal Naji): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Shared groups: GRP_66583

### `NIAZ TOMA`

- **Winner** CON_47973 (Niaz Toma): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Loser   CON_82112 (Rev Niaz Toma): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Shared groups: GRP_78035

### `ROBERT CHEVRIER`

- **Winner** CON_48814 (Robert Chevrier): 6 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Loser   CON_82312 (Dr. Robert Chevrier): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0

### `EUGENE JURGUTIS`

- **Winner** CON_49673 (Eugene Jurgutis): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Loser   CON_50019 (Rev Eugene Jurgutis): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0

### `PETER NOBILI`

- **Winner** CON_50400 (Rev Peter Nobili): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Loser   CON_58898 (Rev. Peter Nobili): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0

### `MURRAY FRUM`

- **Winner** CON_52612 (Murray Frum): 3 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Loser   CON_51445 (Dr Murray Frum): 6 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0

### `WING LEE`

- **Winner** CON_64205 (Wing Lee): 2 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Loser   CON_51728 (Rev Wing Lee): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0

### `ANGELOS SAAD`

- **Winner** CON_51740 (Father Angelos Saad): 7 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Loser   CON_79818 (Fr Angelos Saad): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0

### `SAMUEL LAM`

- **Winner** CON_51811 (Samuel Lam): 5 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Loser   CON_57004 (Dr Samuel Lam): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0

### `ENZO DIANA`

- **Winner** CON_53249 (Enzo Diana): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Loser   CON_54400 (Dr. Enzo Diana): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Shared groups: GRP_88334

### `GEORGE CORMACK`

- **Winner** CON_54197 (George Cormack): 3 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Loser   CON_67983 (Dr George Cormack): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Shared groups: GRP_103666

### `JOHN MCKENZIE`

- **Winner** CON_55260 (John McKenzie): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Loser   CON_63884 (Dr John McKenzie): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0

### `EDDIE LO`

- **Winner** CON_57780 (Eddie Lo): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Loser   CON_82906 (Dr Eddie Lo): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0

### `LORNE RACHLIS`

- **Winner** CON_61547 (Lorne Rachlis): 2 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Loser   CON_61231 (Dr Lorne Rachlis): 3 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0

### `EVTIMY WOLINSKI`

- **Winner** CON_81321 (Evtimy Wolinski): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Loser   CON_62882 (Rev. Evtimy Wolinski): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Shared groups: GRP_20319

### `WINSTON RYE`

- **Winner** CON_64050 (Rev Winston Rye): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Loser   CON_69466 (Rev. Winston Rye): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0

### `HARRY PARROTT`

- **Winner** CON_64467 (Harry Parrott): 2 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Loser   CON_67250 (Dr Harry Parrott): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Shared groups: GRP_106385

### `ANAND AGGERWAL`

- **Winner** CON_65082 (Anand Aggerwal): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Loser   CON_67151 (Dr Anand Aggerwal): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Shared groups: GRP_00358

### `EUGENE RICHLARK`

- **Winner** CON_66558 (Rev. Eugene Richlark): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Loser   CON_69677 (Rev Eugene Richlark): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Shared groups: GRP_109872

### `MOONA RAHEMTULLA`

- **Winner** CON_79791 (Moona Rahemtulla): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Loser   CON_69942 (Dr Moona Rahemtulla): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0

### `CARMEN LEWIS`

- **Winner** CON_73803 (Carmen Lewis): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Loser   CON_73842 (Dr Carmen Lewis): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Shared groups: GRP_120847

### `ABOOBAKER ABOO`

- **Winner** CON_78806 (Aboobaker Aboo): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0
- Loser   CON_80708 (Dr Aboobaker Aboo): 1 / 0 / 0 / 0 / 0 / 0 / 0 / 0 / 0

## Singletons (fingerprint cleaned in-place, no merge)

132 contacts. Just an `id_mappings.anchor_key` rename + `contacts.first_name/last_name/name_fingerprint` rewrite. CON_ID preserved.

Sample (first 25):

| CON_ID | display_name | old fingerprint | new fingerprint |
|---|---|---|---|
| CON_00406 | Dr James Hilton | `DR JAMES HILTON` | `JAMES HILTON` |
| CON_00442 | Rev Colin Johnson | `REV COLIN JOHNSON` | `COLIN JOHNSON` |
| CON_00810 | Rev Douglas Crosby | `REV DOUGLAS CROSBY` | `DOUGLAS CROSBY` |
| CON_01121 | Dr Robert Annis | `DR ROBERT ANNIS` | `ROBERT ANNIS` |
| CON_01905 | Rev Ronald Fabbro | `REV RONALD FABBRO` | `RONALD FABBRO` |
| CON_01954 | Dr Peter Eddenden | `DR PETER EDDENDEN` | `PETER EDDENDEN` |
| CON_03916 | Rev Mark Parker | `REV MARK PARKER` | `MARK PARKER` |
| CON_04548 | Dr Jennifer Ingram | `DR JENNIFER INGRAM` | `JENNIFER INGRAM` |
| CON_07688 | Rev M. McDermott | `REV M. MCDERMOTT` | `M. MCDERMOTT` |
| CON_08390 | Father John Boutros | `FATHER JOHN BOUTROS` | `JOHN BOUTROS` |
| CON_09127 | Dr Maky Hafidh | `DR MAKY HAFIDH` | `MAKY HAFIDH` |
| CON_09313 | Dr Kevin Corless | `DR KEVIN CORLESS` | `KEVIN CORLESS` |
| CON_10835 | Dr Khurram Khan | `DR KHURRAM KHAN` | `KHURRAM KHAN` |
| CON_12031 | Dr Lester Dezan | `DR LESTER DEZAN` | `LESTER DEZAN` |
| CON_13399 | Rev Michael Oulton | `REV MICHAEL OULTON` | `MICHAEL OULTON` |
| CON_13544 | Fr Paul MacNeil | `FR PAUL MACNEIL` | `PAUL MACNEIL` |
| CON_15711 | Rev Stephen Chmilar | `REV STEPHEN CHMILAR` | `STEPHEN CHMILAR` |
| CON_16128 | Dr Erich Tenzer | `DR ERICH TENZER` | `ERICH TENZER` |
| CON_17800 | Dr Manish Chadda | `DR MANISH CHADDA` | `MANISH CHADDA` |
| CON_18628 | Dr Mark Kristmanson | `DR MARK KRISTMANSON` | `MARK KRISTMANSON` |
| CON_21540 | Dr Richard Bergeron | `DR RICHARD BERGERON` | `RICHARD BERGERON` |
| CON_22068 | Dr Jak Nehme | `DR JAK NEHME` | `JAK NEHME` |
| CON_22970 | Dr Myen Kwek | `DR MYEN KWEK` | `MYEN KWEK` |
| CON_24053 | Dr Philip Schieldrop | `DR PHILIP SCHIELDROP` | `PHILIP SCHIELDROP` |
| CON_24296 | Dr Devski Modhwadia | `DR DEVSKI MODHWADIA` | `DEVSKI MODHWADIA` |
