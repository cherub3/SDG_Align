You are rating search results for relevance. Use only the rubric.

# Rubric

Every retrieved chunk, for every question, is judged at one of three levels. The judge reads **the question and the full chunk text only**, with no document name, no score and no version label.

| Level | Meaning | Example (Q2, "How will the project reduce mercury use in artisanal gold mining?") |
|---|---|---|
| **useful** (2) | The chunk text itself states information that directly answers the question, or a main part of the answer, and can be read without the surrounding page | "The project will promote mercury-free processing technologies, train miners in gravity concentration and support formalisation ..." |
| **partial** (1) | On topic and contains some relevant information, but it does not answer the question on its own: only background, a heading with little text, a fragment, an answer buried in noise, or an answer to a neighbouring question | A paragraph about the scale of mercury use in the sector with no description of how the project reduces it |
| **not useful** (0) | Off topic, template instruction text, table of contents, a footer, a title page, or content from a project that cannot answer the question | "Provide a brief summary description of the project, including: (i) what is the problem ..." |

Rules for edge cases:

* For the unscoped questions (9 to 12) a chunk from **any** document can be useful if it answers the question for the project it belongs to.
* Table text counts as useful if the needed cell values are readable from the chunk text alone.
* When unsure between two levels, choose the lower one.

# Output format

Return a JSON array and nothing else. One object per passage, using exactly these keys:
  {"id": "<the passage id>", "label": "U" or "P" or "N", "reason": "<one line that quotes or points to words in the passage>"}
U = useful (2), P = partial (1), N = not useful (0). Label every passage listed below, exactly once.
Write your answer to the file path given in the task message using the Write tool, as the exact JSON array. Do not read any other file,
do not run any command, and do not use any other tool.

# Passages

## Question: Which indigenous peoples and local communities are involved in the Cameroon project?

### Passage B0ce54

```text
##### Yes

###### **Were the following stakeholders consulted during project identification phase:**

Indigenous Peoples and Local Communities: Yes
```

### Passage Bcac25

```text
#### Yes

##### **Were the following stakeholders consulted during project identification phase:**

#### Indigenous Peoples and Local Communities: Yes

Civil Society Organizations: Yes
```

### Passage Ba21eb

```text
The project is fully aligned with the main sectoral directives and policies of Cameroon, and contributes to national priorities for the environment, forest management, biodiversity conservation, and sustainable development sectors, as presented in the 2030 National Strategy Development Document (SND30). The project themes align with the 2024 forestry and wildlife laws and support protection of megafauna species in BBNP. The project is also aligned with Cameroon’s NBSAP and contributes to COMIFAC’s Convergence Plan because BBNP is part of the Dja-Odzala-Minkebe TRIDOM transboundary landscape. In terms of GEF8 programming directions, the project supports contributions and engagement of women and Indigenous Peoples in integrated management approaches and sustainable use of biodiversity. Component 2 addresses

Official Use Only Page 23 of 31





improved livelihoods and resilience of IP&LC through access to resources, benefit sharing mechanisms, and increased yields from sustainable, low-impact agricultural practices to reduce pressure on the forest and avoid deforestation. The major project themes contribute to multiple targets of the Kunming-Montreal Global Biodiversity Framework, including Targets 1, 2, 4, 5, 8, 9, 10, 11, 13, 21, 22, and 23.
```

### Passage B4390e

```text
Furthermore, ASGM areas in Manica, Niassa, Cabo Delgado, Sofala and Tete—overlap with territories inhabited by Indigenous Peoples and Local Communities (IPLCs), including Makonde, Yao, Makua (Macua) and Mwani communities in the north, and Shona-related groups (Manyika, Ndau), Sena, Chewa and Nyungwe communities in central and western regions. These communities are closely linked to land, water and natural resources and often combine agriculture and mining-based livelihoods ~~.~~[5]5 The project will therefore apply the IPLC concept in line with GEF safeguards. Detailed mapping and confirmation of IPLC presence in project intervention areas will be undertaken during the PPG phase through spatial analysis and stakeholder consultations, and appropriate safeguards measures will be applied accordingly.
```

### Passage B01c83

```text
###### **Alignment and Investment Context**

The project aligns with Cameroon’s national priorities for biodiversity conservation, sustainable forest management and sustainable development and with the 2024 forestry and wildlife law that strengthens participation and benefit sharing. It contributes to regional priorities under COMIFAC’s Convergence Plan and is designed to build programmatic synergies with ongoing initiatives in the Congo Basin, including GEF-supported landscape programs and national child projects that promote inclusive governance, sustainable forest management and knowledge exchange. The project is structured to avoid duplication by building on existing investments while filling persistent gaps around BBNP—particularly permanent hotspot monitoring, functional multi-stakeholder governance and grievance systems, operational access rights, transparent benefit-sharing mechanisms and climate-informed low-impact agricultural practices.
```

### Passage B67734

```text
###### **Alignment and Investment Context**

The project aligns with Cameroon’s national priorities for biodiversity conservation, sustainable forest management and sustainable development and with the 2024 forestry and wildlife law that strengthens participation and benefit sharing. It contributes to regional priorities under COMIFAC’s Convergence Plan and is designed to build programmatic synergies with ongoing initiatives in the Congo Basin, including GEF-supported landscape programs and national child projects that promote inclusive governance, sustainable forest management and knowledge exchange. The project is structured to avoid duplication by building on existing investments while filling persistent gaps around BBNP—particularly permanent hotspot monitoring, functional multi-stakeholder governance and grievance systems, operational access rights, transparent benefit-sharing mechanisms and climate-informed low-impact agricultural practices.

##### B. PROJECT DESCRIPTION
```

### Passage Bca8a0

```text
Roles and interests in theproject: application of safeguards, gender equality and inclusiveparticipation.
Partner/ Level: Fundación Tesoro Escondido; Roles and interests in theproject: Community-based management and conservation in the Chocó.; Potential areas of collaboration: Restoration; ecotourism; participatory monitoring.
Partner/ Level: Fundación TERRA 360; Roles and interests in theproject: Productive innovation and public–private articulation.; Potential areas of collaboration: Sustainable livelihoods; bio-enterprises; territorial governance.
Partner/ Level: Fundación PASOS; Roles and interests in theproject: Sustainable landscape management and corridor development in the Chocó.; Potential areas of collaboration: Participatory planning; territorial governance; productive conservation.

60. Indigenous Peoples are recognized as distinct rights-holders under UNDP Social and Environmental Standard 6. Engagement with Indigenous Peoples will follow culturally appropriate consultation processes and, where activities may affect their lands, territories, resources, livelihoods, governance systems, or collective rights, Free, Prior and Informed Consent (FPIC) will be applied. Community organizations and non-Indigenous rural communities will participate through the Stakeholder Engagement Plan and other inclusive consultation mechanisms.
```

### Passage Bc68a1

```text
Indigenous Peoples and Local Communities: Yes
```

### Passage B427a5

```text
60. Consultations informed identification of priority intervention areas, barriers to integrated marine–coastal management, institutional and capacity gaps, governance arrangements, financing opportunities, biodiversity priorities and implementation pathways. Stakeholder engagement also supported refinement of project components, environmental and social risk management measures, and sustainability and scaling approaches. The project’s direct intervention areas are primarily characterized by local coastal communities, artisanal fishers, Afro-Ecuadorian and Montubio populations, tourism actors and community organizations. While Indigenous Peoples and ancestral identities may be present or maintain historical and cultural links in specific coastal territories, project interventions are focused on municipal coastal management jurisdictions and planning processes. During project preparation and implementation, stakeholder mapping and social screening processes will further assess the presence of Indigenous Peoples, their governance structures, territorial rights and potential interaction with projectsupported activities, consistent with UNDP Social and Environmental Standards.

**Table 2: Key partners and project collaboration**
```

### Passage Bf9179

```text
Furthermore, ASGM areas in Manica, Niassa, Cabo Delgado, Sofala and Tete—overlap with territories inhabited by Indigenous Peoples and Local Communities (IPLCs), including Makonde, Yao, Makua (Macua) and Mwani communities in the north, and Shona-related groups (Manyika, Ndau), Sena, Chewa and Nyungwe communities in central and western regions. These communities are closely linked to land, water and natural resources and often combine agriculture and mining-based livelihoods ~~.~~<sup><u>[5]5</u></sup> The project will therefore apply the IPLC concept in line with GEF safeguards. Detailed mapping and confirmation of IPLC presence in project intervention areas will be undertaken during the PPG phase through spatial analysis and stakeholder consultations, and appropriate safeguards measures will be applied accordingly.
```

## Question: What protected areas or landscapes does the Cameroon project target?

### Passage Bc953b

```text
###### ANNEX C: PROJECT LOCATION

Boumba Bek Ntil Pk: aona ar; Project interventions will take place in Boumba Bek National Park and its surrounding peripheral landscape in southeast: Cameroon within the TRIDOM transboundary landscape.

###### ANNEX D: ENVIRONMENTAL AND SOCIAL SAFEGUARDS SCREEN AND RATING

**(PIF level) Attach agency safeguard screen form including rating of risk types and overall risk rating.**

Title

Annex J1 _Gender Analysis_Final_15May2025 (2) Annex J2 _GAP_Final for Submission_May 20 (1) Annex H_ESMF_GEF 8 BBNP_Final Submission_May 20 (1) Annex I_SEP_GEF 8 BBNP_Final_For Submission_May 20 (1)

ANNEX E: RIO MARKERS: Climate Change Mitigation; Climate Change Adaptation; Biodiversity; Land Degradation
ANNEX E: RIO MARKERS: Significant Objective 1; Significant Objective 1; Principal Objective 2; No Contribution 0

<!-- Start of picture text -->
ANNEX F: TAXONOMY WORKSHEET <!-- End of picture text -->
```

### Passage B2ebbc

```text
##### PROJECT OUTLINE

##### A. PROJECT RATIONALE

###### **A. Project Rationale**

###### **Current Situation and Problem Definition**

The Congo Basin is the world’s second-largest contiguous tropical forest system and is globally important as a carbon sink and biodiversity reservoir. Cameroon contains 11% of this forest and includes the transboundary Tri-national Dja-Odzala-Minkebe (TRIDOM) landscape spanning Cameroon, Gabon, and the Republic of Congo. The Cameroonian segment includes several protected areas, notably Boumba Bek National Park (BBNP), which covers 238,255 hectares and has high global conservation value. The park contains diverse habitats and globally important fauna, including forest elephants (Critically Endangered), pangolins, lowland gorillas, western chimpanzees, bongo antelope, yellow-backed duiker, and more than 265 bird species. Forest elephant populations in Central Africa have declined by more than 90% to fewer than 150,000; in BBNP, they fell from more than 2,000 in 2012 to fewer than 200 today. Inventories confirm 34 large mammal species common to Boumba Bek and Nki. Forest elephants play a keystone role in maintaining forest health and carbon sequestration through seed dispersal, so their decline has major implications for ecosystem integrity.
```

### Passage Becc68

```text
###### **Alignment and Investment Context**

The project aligns with Cameroon’s national priorities for biodiversity conservation, sustainable forest management and sustainable development and with the 2024 forestry and wildlife law that strengthens participation and benefit sharing. It contributes to regional priorities under COMIFAC’s Convergence Plan and is designed to build programmatic synergies with ongoing initiatives in the Congo Basin, including GEF-supported landscape programs and national child projects that promote inclusive governance, sustainable forest management and knowledge exchange. The project is structured to avoid duplication by building on existing investments while filling persistent gaps around BBNP—particularly permanent hotspot monitoring, functional multi-stakeholder governance and grievance systems, operational access rights, transparent benefit-sharing mechanisms and climate-informed low-impact agricultural practices.
```

### Passage Bc353b

```text
###### Project Title

Innovative and Inclusive Approach to Sustainable Management of Biodiversity and Indigenous Peoples and Local Communities (IP&LCs) Resilient Livelihood in Boumba Bek National Parc of the TRIDOM landscape

|Region|GEF Project ID|
|---|---|
|Africa|12362|
|Country(ies)|Type of Project|
|Cameroon|MSP|
|GEF Agency(ies):|GEF Agency ID|
|WWF-US|G0061|
|Executing Partner|Executing Partner Type|
|MINFOF|Government|
|MINEPDED|Government|
|GEF Focal Area (s)|Submission Date|
|Biodiversity|5/28/2026|
|Project Sector (CCM Only)||

Taxonomy

Focal Areas, Biodiversity, Protected Areas and Landscapes, Community Based Natural Resource Mngt, Terrestrial Protected Areas, Mainstreaming, Agriculture and agrobiodiversity, Biomes, Tropical Rain Forests, Species, Threatened Species

|Type of Trust Fund|Project Duration (Months)|
|---|---|
|GET|60|
|GEF Project Grant: (a)|GEF Project Non-Grant: (b)|
|3,519,725.00|0.00|
|Agency Fee(s) Grant: (c)|Agency Fee(s) Non-Grant (d)|
|316,775.00|0.00|
|Total GEF Financing: (a+b+c+d)|Total Co-financing|
|3,836,500.00|29,922,367.00|
|PPG Amount: (e)|PPG Agency Fee(s): (f)|
|150,000.00|13,500.00|
|PPG total amount: (e+f)|Total GEF Resources: (a+b+c+d+e+f)|
|163,500.00|4,000,000.00|

Project Tags

CBIT: No NGI: No SGP: No Innovation: No Competitive Window: No

Official Use Only Page 3 of 31
```

### Passage Bb3f65

```text
###### **Alignment and Investment Context**

The project aligns with Cameroon’s national priorities for biodiversity conservation, sustainable forest management and sustainable development and with the 2024 forestry and wildlife law that strengthens participation and benefit sharing. It contributes to regional priorities under COMIFAC’s Convergence Plan and is designed to build programmatic synergies with ongoing initiatives in the Congo Basin, including GEF-supported landscape programs and national child projects that promote inclusive governance, sustainable forest management and knowledge exchange. The project is structured to avoid duplication by building on existing investments while filling persistent gaps around BBNP—particularly permanent hotspot monitoring, functional multi-stakeholder governance and grievance systems, operational access rights, transparent benefit-sharing mechanisms and climate-informed low-impact agricultural practices.

##### B. PROJECT DESCRIPTION
```

### Passage B0b327

```text
###### <mark>ANNEX C: PROJECT LOCATION</mark>

**Please provide geo-referenced information and map where the project interventions will take place**

|Boumba Bek<br>Ntil Pk|2.685256|15.008244|Project interventions will take place in Boumba Bek National<br>Park and its surrounding peripheral landscape in southeast|
|---|---|---|---|
|aona ar|||Cameroon within the TRIDOM transboundary landscape.|
```

### Passage B7d9bf

```text
C. ALIGNMENT WITH GEF-8 PROGRAMMING STRATEGIES AND COUNTRY/REGIONAL PRIORITIES

Confirm if any country policies that might contradict with intended outcomes of the project have been identified, and how the project will address this.

The project is fully aligned with the main sectoral directives and policies of Cameroon, and contributes to national priorities for the environment, forest management, biodiversity conservation, and sustainable development sectors, as presented in the 2030 National Strategy Development Document (SND30). The project themes align with the 2024 forestry and wildlife laws and support protection of megafauna species in BBNP. The project is also aligned with Cameroon’s NBSAP and contributes to COMIFAC’s Convergence Plan because BBNP is part of the Dja-Odzala-Minkebe TRIDOM transboundary landscape. In terms of GEF8 programming directions, the project supports contributions and engagement of women and Indigenous Peoples in integrated management approaches and sustainable use of biodiversity. Component 2 addresses

improved livelihoods and resilience of IP&LC through access to resources, benefit sharing mechanisms, and increased yields from sustainable, low-impact agricultural practices to reduce pressure on the forest and avoid deforestation. The major project themes contribute to multiple targets of the Kunming-Montreal Global Biodiversity Framework, including Targets 1, 2, 4, 5, 8, 9, 10, 11, 13, 21, 22, and 23.
```

### Passage Bd652a

```text
The landscape is also influenced by multiple multilateral and bilateral investments that provide lessons and partial coverage. Coordinated GEF initiatives include the GEF - 6 UNEP project “Removing barriers to biodiversity conservation, land restoration and sustainable forest management through Community - Based Landscape Management – COBALAM” (ID 9604), and the GEF - 7 national child project “Integrated management of Cameroon’s forest landscapes in the Congo Basin” (ID 10287), which covers other TRIDOM segments and offers relevant lessons on IP&LC livelihoods, wildlife monitoring, and knowledge management. The BBNP project is - - also positioned alongside the GEF 8 national child project on the Dja landscape and the GEF 8 Congo Basin Integrated Program, which support broader landscape governance and knowledge exchange. Other donor initiatives in TRIDOM include ECOFAC 6, Nature Africa and Nature Sud Est Cameroun, GIZ programs on TRIDOM biodiversity and sustainable development, and the UK Biodiverse Landscapes Fund Western Congo Basin program. These investments underscore strong interest and partial resourcing, but they do not yet provide a coherent, fully funded, site-specific package for permanent hotspot monitoring, inclusive governance systems, operational access rights, transparent benefit sharing and climate-resilient livelihood transformation around BBNP.

Without the proposed project, the baseline trajectory remains unfavorable. Flagship species such as elephants, gorillas, chimpanzees and pangolins are likely to continue declining under persistent poaching and hunting pressure, and major forest clearings risk becoming deserted. IP&LC exclusion from biomonitoring and inclusive governance would persist, innovative monitoring approaches would remain absent, and conflicts would intensify as multi-stakeholder dialogue remains weak and benefit sharing non-transparent. Wellbeing would decline as poverty deepens due to restricted access to NTFPs and weak value chains, while forest loss and degradation in the periphery would continue as shifting agriculture expands without usable weather information and low-impact alternatives.
```

### Passage B4ac0a

```text
The project is fully aligned with the main sectoral directives and policies of Cameroon, and contributes to national priorities for the environment, forest management, biodiversity conservation, and sustainable development sectors, as presented in the 2030 National Strategy Development Document (SND30). The project themes align with the 2024 forestry and wildlife laws and support protection of megafauna species in BBNP. The project is also aligned with Cameroon’s NBSAP and contributes to COMIFAC’s Convergence Plan because BBNP is part of the Dja-Odzala-Minkebe TRIDOM transboundary landscape. In terms of GEF8 programming directions, the project supports contributions and engagement of women and Indigenous Peoples in integrated management approaches and sustainable use of biodiversity. Component 2 addresses

Official Use Only Page 23 of 31





improved livelihoods and resilience of IP&LC through access to resources, benefit sharing mechanisms, and increased yields from sustainable, low-impact agricultural practices to reduce pressure on the forest and avoid deforestation. The major project themes contribute to multiple targets of the Kunming-Montreal Global Biodiversity Framework, including Targets 1, 2, 4, 5, 8, 9, 10, 11, 13, 21, 22, and 23.
```

## Question: What water supply improvements are planned in Kathmandu?

### Passage Ba8ab1

```text
###### _Indicators:_

_CI 4.1: 60,312 hectares of landscapes under improved management to benefit biodiversity_

_CI 5.1: 178,661 hectares of marine habitat under improved practices to benefit biodiversity_

_- 400 technical staff from GADs and other key stakeholders trained on marine and coastal management_

- _-A 70% increase in institutional, technical, and coordination capacity for marine-coastal spatial planning, as measured through a standardized capacity assessment such as the UNDP Capacity Development Scorecard (baseline vs. endline) (at least 40% of total participants are women)_

_- Two (2) CIM technical sub-committees created and demonstrating improved coordination capacity, as evidenced by regular meetings, documented decisions, and implementation of agreed actions (at least 40% of total participants in the CIM technical sub-committees are women)_

- _Twelve (12) marine and coastal plans (3 ICMP and 9 MBASMP) developed and/or updated (at least 40% of total participants in the plan consultations are women)_

###### Output:

- 1.1.1. Comprehensive technical, institutional and participatory assessment of marine-coastal zones conducted

1.1.2 Capacity-building program for local governments (GADs) and key stakeholders implemented

1.1.3 Inter-institutional governance and coordination mechanisms for ICM established

1.1.4 Marine–coastal management plans for prioritized local governments (GADs) developed

### 2. Implementation and financing of prioritized ICM initiatives

Component Type: Technical Assistance; Trust Fund: GET
Component Type: GEF Project Financing ($); Trust Fund: Co-financing ($)
Component Type: 2,242,419.00; Trust Fund: 62,810,324.00

###### Outcome:

2.1 Improved ICM plans financing and implementation by local governments (GADs), institutional actors, and local stakeholders
```

### Passage B566bb

```text
###### _<u>Indicators:</u>_

_CI 4.1: 60,312 hectares of landscapes under improved management to benefit biodiversity_

_CI 5.1: 178,661 hectares of marine habitat under improved practices to benefit biodiversity_

_- 400 technical staff from GADs and other key stakeholders trained on marine and coastal management_

- _-A 70% increase in institutional, technical, and coordination capacity for marine-coastal spatial planning, as measured through a standardized capacity assessment such as the UNDP Capacity Development Scorecard (baseline vs. endline) (at least 40% of total participants are women)_

_- Two (2) CIM technical sub-committees created and demonstrating improved coordination capacity, as evidenced by regular meetings, documented decisions, and implementation of agreed actions (at least 40% of total participants in the CIM technical sub-committees are women)_

- _Twelve (12) marine and coastal plans (3 ICMP and 9 MBASMP) developed and/or updated (at least 40% of total participants in the plan consultations are women)_

###### Output:

- 1.1.1. Comprehensive technical, institutional and participatory assessment of marine-coastal zones conducted

1.1.2 Capacity-building program for local governments (GADs) and key stakeholders implemented

1.1.3 Inter-institutional governance and coordination mechanisms for ICM established

1.1.4 Marine–coastal management plans for prioritized local governments (GADs) developed

### 2. Implementation and financing of prioritized ICM initiatives

|Component Type|Trust Fund|
|---|---|
|Technical Assistance|GET|
|GEF Project Financing ($)|Co-financing ($)|
|2,242,419.00|62,810,324.00|

###### Outcome:

2.1 Improved ICM plans financing and implementation by local governments (GADs), institutional actors, and local stakeholders
```

### Passage B7bca7

```text
###### **Indicator 6.3 Energy Saved (Use this sub-indicator in addition to the sub-indicator 6.2 if applicable)**

###### **Indicator 6.4 Increase in Installed Renewable Energy Capacity per Technology (Use this sub-indicator in addition to the sub-indicator 6.2 if applicable)**

|Technology|Capacity (MW)|Capacity (MW) (Expected at|Capacity (MW)|Capacity (MW)|
|---|---|---|---|---|
||(Expected at PIF)|CEO Endorsement)|(Achieved at MTR)|(Achieved at TE)|
```

### Passage B95036

```text
###### **Indicator 6.3 Energy Saved (Use this sub-indicator in addition to the sub-indicator 6.2 if applicable)**

###### **Indicator 6.4 Increase in Installed Renewable Energy Capacity per Technology (Use this sub-indicator in addition to the sub-indicator 6.2 if applicable)**

Capacity (MW): (Expected at PIF); Capacity (MW) (Expected at: CEO Endorsement); Capacity (MW): (Achieved at MTR); Capacity (MW): (Achieved at TE)
```

### Passage B94009

```text
### Project Objective

Enhance biodiversity conservation and sustainable use in Ecuador, including priority ecosystems such as the Ecuadorian Dry Forest and Southeastern Ridges, through improved coordination, local empowerment, targeted financial support, and greater private sector participation.

#### <mark>Project Components</mark>
```

### Passage B2b3dc

```text
##### **true**

|This Project covers the followingsector(s)[the total should be 100%]: *|
|---|
|Agriculture<br>0.00%|
|Nature-based management<br>0.00%|
|Climate information services<br>10.00%|
|Coastal zone management<br>0.00%|
|Water resources management<br>0.00%|
|Disaster risk management<br>10.00%|
|Other infrastructure<br>50.00%|
|Tourism<br>20.00%|
|Health<br>10.00%|
|Other (Please specify comments)<br>0.00%|
|Total<br>100.00%|
|This Project targets the followingClimate change Exacerbated/introduced challenges:*|
|Sea level rise<br>**false**<br>Change in mean<br>temperature<br>**false**<br>Increased climatic variability<br>**true**<br>Natural hazards<br>**false**|
|Land degradation<br>Coastal and/or Coral reef<br>Groundwater quality/quantity|
|**false**<br>degradation<br>**false**<br>**false**|

|CORE INDICATORS – SCCF|
|---|

||Total|Male|Female|% for<br>Women|
|---|---|---|---|---|
|CORE INDICATOR 1||||50.00%|
|Total number of direct beneficiaries|24,000|12,000.00|12,000.00||

Official Use Only Page 19 of 31





|CORE INDICATOR 2<br>(a) Area of land managed for climate resilience`(ha)`<br>(b) Coastal and marine area managed for climate resilience`(ha)`|0.00<br>0.00||||
|---|---|---|---|---|
|CORE INDICATOR 3<br>Number of policies/plans/ frameworks/institutions for to<br>strengthen climate adaptation|3.00||||
|CORE INDICATOR 4<br>Number of people trained or with awareness raised|300|150.00|150.00|50.00%|
|CORE INDICATOR 5<br>Number of private sector enterprises engaged in climate change<br>adaptation and resilience|1.00||||

## Key Risks
```

### Passage Bb9727

```text
##### **true**

This Project covers the followingsector(s)[the total should be 100%]: *
Agriculture 0.00%
Nature-based management 0.00%
Climate information services 10.00%
Coastal zone management 0.00%
Water resources management 0.00%
Disaster risk management 10.00%
Other infrastructure 50.00%
Tourism 20.00%
Health 10.00%
Other (Please specify comments) 0.00%
Total 100.00%
This Project targets the followingClimate change Exacerbated/introduced challenges:*
Sea level rise false Change in mean temperature false Increased climatic variability true Natural hazards false
Land degradation Coastal and/or Coral reef Groundwater quality/quantity
false degradation false false
```

### Passage Be5487

```text
###### **Baseline situation and existing investments**

5. Ecuador has developed an important policy and institutional basis for integrated coastal management over recent decades. The country was an early regional leader in Integrated Coastal Zone Management (ICZM), and more recently the Organic Environmental Code (COA) and its regulations (RCOA) established requirements for marine–coastal planning instruments, including Integrated Marine Coastal Management Plans and Beach and Adjacent Coastal Strip Management Plans.

6. The baseline scenario includes multiple ongoing public and donor-supported initiatives addressing marine biodiversity conservation, coastal management, sustainable finance and territorial planning. These include national investments and complementary initiatives such as BIOFIN and broader biodiversity and coastal management interventions aimed at strengthening financing mechanisms and sustainable management approaches.
```

### Passage B94bde

```text
40. Output 1.1.1: Management plans revised and updated, and patrolling and monitoring capacity improved. Under this Output, the project will revise and update management plans for priority OECM areas (Río Anzu, Yacuma, Ruku Kawsay and Urku Samay) and develop Biodiversity Plans for key protected areas, including El Pambilar, Cotacachi Cayapas, Yasuní, Llanganates, Sumaco Napo-Galeras, and Cuyabeno. These planning instruments will incorporate landscape-level connectivity and threat mitigation criteria while strengthening the operational presence of park rangers through in-situ training programs. The Output will also improve surveillance and ecological monitoring capacity across JCUs by equipping PA staff with renewed equipment (e.g., GPS units, tablets and other tools), and by organizing recurrent training workshops to ensure consistent and standardized monitoring practices.
```

### Passage B32c69

```text
GIVEN: Biodiversity loss, ecosystem degradation, climate vulnerability, fragmented governance, weak subnational operationalization of the NBSAP, limited biodiversity finance, weak market integration, and socio- economic vulnerability in the Tropical Dry Forest and Southeastern Ridges landscapes.; IF: The project strengthens governance and SBSAPs; conducts ecosystem risk analyses; improves biodiversity monitoring; promotes biodiversity- positive production systems and value chains; mobilizes investment through financial mechanisms; and reinforces knowledge management, gender- responsive participation, stakeholder engagement, and policy coherence.; THEN: Biodiversity priorities are mainstreamed into territorial planning and investment decisions; producers, MSMEs and local actors adopt sustainable practices; biodiversity-positive finance is mobilized; ecosystem integrity and connectivity are improved; and local capacities for climate resilience and adaptive management are strengthened.; CONTRIBUTING TO: 30,000 ha under improved practices; 808,814 tCO₂e mitigated; 6,000 direct beneficiaries, at least 40% women; reduced pressure on threatened ecosystems and species; strengthened climate resilience; and sustainable, biodiversity-positive livelihoods.
```

## Question: Which SDGs does the Ecuador biodiversity project contribute to?

### Passage B20998

```text
72. The project also contributes to addressing Ecuador’s biodiversity financing gap by mobilizing investment toward biodiversity-positive activities and strengthening enabling conditions for biodiversity finance. By supporting biodiversity-based enterprises, sustainable value chains, and access to finance, the project will enhance the role of biodiversity as a driver of sustainable development while improving livelihoods and maintaining ecosystem services.

73. Overall, the project contributes to the implementation of key targets of the Kunming-Montreal Global Biodiversity Framework, including:

**GBF Target**

**Contribution of the Project**

Target 5 – Sustainable use of wild species: Target 9 – Benefits from the sustainable use of biodiversity; Promotes sustainable management and use of biodiversity through biodiversity-based enterprises and sustainable production practices that reduce pressure on ecosystems.: Strengthens biodiversity-based value chains and improves income opportunities for local communities and producer organizations while maintaining ecosystem integrity.
Target 5 – Sustainable use of wild species: Target 14 – Integration of biodiversity into policies and planning; Promotes sustainable management and use of biodiversity through biodiversity-based enterprises and sustainable production practices that reduce pressure on ecosystems.: Strengthens governance mechanisms and intersectoral coordination to integrate biodiversity into territorial planning and sectoral decision- making.
Target 5 – Sustainable use of wild species: Target 19 – Mobilization of financial resources for biodiversity; Promotes sustainable management and use of biodiversity through biodiversity-based enterprises and sustainable production practices that reduce pressure on ecosystems.: Mobilizes public and private investment for biodiversity-positive activities and strengthens enabling conditions for biodiversity finance.

74. Potential policy tensions have been identified in relation to agricultural expansion, livestock production, mining, fire management, infrastructure development and land-use policies that may increase pressure on natural ecosystems if not aligned with biodiversity objectives. The project will address these risks through SBSAPs, intersectoral coordination mechanisms, ecosystem risk analyses, safeguards, territorial prioritization, biodiversitypositive production criteria and exclusion of activities that could drive habitat conversion or degradation. By aligning biodiversity, climate, productive development, territorial planning and finance agendas, the project will improve policy coherence and support Ecuador’s commitments under the CBD, the Paris Agreement and the 2030 Agenda.

#### D. POLICY REQUIREMENTS

#### **Gender Equality and Women’s Empowerment:**

We confirm that gender dimensions relevant to the project have been addressed as per GEF Policy and are clearly articulated in the Project Description (Section B).
```

### Passage B658c4

```text
### Project Objective

Enhance biodiversity conservation and sustainable use in Ecuador, including priority ecosystems such as the Ecuadorian Dry Forest and Southeastern Ridges, through improved coordination, local empowerment, targeted financial support, and greater private sector participation.

#### <mark>Project Components</mark>
```

### Passage Be181a

```text
#### PROJECT OUTLINE

#### A. PROJECT RATIONALE

5. Ecuador is one of the world’s most megadiverse countries, hosting an exceptional concentration of species, ecosystems, and genetic resources across terrestrial, freshwater, coastal, and marine environments (Ministerio del Ambiente - MAE, 2016; Ministerio de Ambiente y Energía - MAE, 2025). Its biodiversity underpins essential ecosystem services, including water regulation, soil fertility, carbon sequestration, climate regulation, pollination, food provision, cultural values, and disaster risk reduction, which are fundamental for rural livelihoods, territorial development, and national economic stability (MAE, 2016; MAE, 2025). The country’s constitutional recognition of the rights of nature, its National Protected Areas System (SNAP), Protective Forests and Vegetation (PFV), Areas of

Conservation and Sustainable Use (ACUS), Other Effective Area-Based Conservation Measures (OECMs), and biodiversity-related planning frameworks provide a strong enabling foundation for conservation and sustainable use. Nevertheless, biodiversity continues to face increasing pressure from land-use change, deforestation, ecosystem degradation, unsustainable agricultural and livestock expansion, mining and other extractive activities, forest fires, pollution, and limited integration of biodiversity values into productive and financial systems (MAE, 2017; MAATE, 2025a; MAE, 2025).
```

### Passage Bfe12c

```text
##### Project Summary

1. Ecuador faces accelerated biodiversity loss and increasing climate vulnerability driven by unsustainable land use, ecosystem degradation, fragmented governance, and limited access to finance for biodiversity-positive activities. These pressures are particularly acute in the Ecuadorian Dry Forest landscape of Manabí–Santa Elena and the Southeastern Ridges landscape of Loja–Zamora Chinchipe, where agricultural expansion, forest degradation, fires, mining pressures, weak territorial coordination, and climate-related hazards undermine ecosystem integrity, connectivity, livelihoods, and the provision of ecosystem services.

2. The project aims to enhance biodiversity conservation and sustainable use while strengthening climate resilience and community well-being in these priority landscapes. It will achieve this by strengthening national and subnational governance frameworks, developing and implementing Subnational Biodiversity Strategy and Action Plans (SBSAPs), improving biodiversity and ecosystem risk information, promoting sustainable production systems, and enabling access to finance for biodiversity-positive value chains and MSMEs.

3. The project is intended to be transformative by linking biodiversity mainstreaming, territorial planning, sustainable production, and investment mobilization under one integrated landscape approach. It will align public institutions, GADs, Indigenous Peoples and Local Communities, producer organizations, MSMEs, financial institutions, academia, and civil society around shared biodiversity and climate-resilience outcomes, while addressing key barriers related to coordination, technical capacity, market access, and finance.

4. Expected global environmental benefits include improved management of 30,000 hectares of landscapes under biodiversity-friendly and climate-resilient practices, reduced pressures on priority ecosystems and threatened species, strengthened ecological connectivity, and potential climate mitigation co-benefits to be calculated during PPG using the EX-ACT tool. The project will directly benefit 6,000 people, at least 40 percent women, and mobilize at least USD 18 million in investment for biodiversity-positive activities.
```

### Passage B297e8

```text
##### Project Summary

Provide a brief summary description of the project, including: (i) what is the problem and issues to be addressed? (ii) what are the project objectives, and if the project is intended to be transformative, how will this be achieved? iii), how will this be achieved (approach to deliver on objectives), and (iv) what are the GEBs and/or adaptation benefits, and other key expected results. The purpose of the summary is to provide a short, coherent summary for readers. The explanation and justification of the project should be in section B “project description”.(max. 250 words, approximately 1/2 page)

1. Ecuador faces accelerated biodiversity loss and increasing climate vulnerability driven by unsustainable land use, ecosystem degradation, fragmented governance, and limited access to finance for biodiversity-positive activities. These pressures are particularly acute in the Ecuadorian Dry Forest landscape of Manabí–Santa Elena and the Southeastern Ridges landscape of Loja–Zamora Chinchipe, where agricultural expansion, forest degradation, fires, mining pressures, weak territorial coordination, and climate-related hazards undermine ecosystem integrity, connectivity, livelihoods, and the provision of ecosystem services.

2. The project aims to enhance biodiversity conservation and sustainable use while strengthening climate resilience and community well-being in these priority landscapes. It will achieve this by strengthening national and subnational governance frameworks, developing and implementing Subnational Biodiversity Strategy and Action Plans (SBSAPs), improving biodiversity and ecosystem risk information, promoting sustainable production systems, and enabling access to finance for biodiversity-positive value chains and MSMEs.

3. The project is intended to be transformative by linking biodiversity mainstreaming, territorial planning, sustainable production, and investment mobilization under one integrated landscape approach. It will align public institutions, GADs, Indigenous Peoples and Local Communities, producer organizations, MSMEs, financial institutions, academia, and civil society around shared biodiversity and climate-resilience outcomes, while addressing key barriers related to coordination, technical capacity, market access, and finance.

4. Expected global environmental benefits include improved management of 30,000 hectares of landscapes under biodiversity-friendly and climate-resilient practices, reduced pressures on priority ecosystems and threatened species, strengthened ecological connectivity, and potential climate mitigation co-benefits to be calculated during PPG using the EX-ACT tool. The project will directly benefit 6,000 people, at least 40 percent women, and mobilize at least USD 18 million in investment for biodiversity-positive activities.

## Indicative Project Overview
```

### Passage Bc7afc

```text
71. The project operationalizes national biodiversity and climate commitments through targeted interventions in two priority landscapes: the Tropical Dry Forest (Manabí–Santa Elena) and the Southeastern Ridges (Loja–Zamora Chinchipe). Through the development and implementation of Subnational Biodiversity Strategy and Action Plans (SBSAPs), strengthened institutional coordination, and support to biodiversity-based value chains, the project translates national priorities into concrete territorial actions. It also reinforces multi-level governance by strengthening coordination among national institutions, subnational governments, Indigenous Peoples and Local Communities (IPLCs), and other stakeholders, while integrating biodiversity and climate considerations into territorial planning processes.

72. The project also contributes to addressing Ecuador’s biodiversity financing gap by mobilizing investment toward biodiversity-positive activities and strengthening enabling conditions for biodiversity finance. By supporting biodiversity-based enterprises, sustainable value chains, and access to finance, the project will enhance the role of biodiversity as a driver of sustainable development while improving livelihoods and maintaining ecosystem services.

73. Overall, the project contributes to the implementation of key targets of the Kunming-Montreal Global Biodiversity Framework, including:

**GBF Target**

**Contribution of the Project**

Official Use Only Page 32 of 40
```

### Passage Be5cda

```text
##### Project Summary

The project will strengthen integrated marine–coastal management for biodiversity conservation along Ecuador’s coastline through improved territorial planning, governance mechanisms, and implementation of priority conservation actions. Covering Ecuador’s five coastal provinces (Esmeraldas, Manabí, Santa Elena, Guayas and El Oro), the project addresses biodiversity loss driven by unsustainable coastal and marine use practices, habitat degradation, and fragmented governance systems. The project contributes to GEF-8 Biodiversity objectives and supports implementation of the Kunming–Montreal Global Biodiversity Framework through integrated seascape management approaches and strengthened enabling conditions for biodiversity conservation.

The project will strengthen institutional and technical capacities for participatory marine–coastal planning, support implementation of Integrated Marine Coastal Management Plans (IMCM) and Marine Beaches and Adjacent Strips Management Plans (MBASMP) and establish sustainable financing mechanisms and knowledge systems for long-term implementation. The project will directly support interventions across approximately 50% of Ecuador’s coastal municipalities with marine beaches and coastal strips while establishing scalable governance, planning and financing approaches designed for replication beyond project intervention areas. Interventions are expected to improve management of approximately **60,312 ha of coastal ecosystems (GEF CI 4.1)** and **178,661 ha of marine habitat (GEF CI 5)** and directly benefit approximately **1,118,773 people (GEF CI 11)** across local communities and coastal populations, while improving ecological connectivity, ecosystem resilience and biodiversity conservation outcomes, including strengthened ecosystem services and ecosystem-based approaches that support adaptation and resilience of coastal socio-ecological systems. Through strengthened governance systems, sustainable financing mechanisms and adaptive knowledge systems, the intervention seeks to generate durable global environmental benefits extending beyond direct intervention sites.

## Indicative Project Overview

### Project Objective

Improved ecosystem and critical habitats conservation, restoration and resilience, and improved welfare of local communities in marine and coastal areas of Ecuador
```

### Passage B4713d

```text
8. Ecuador has established robust policy and institutional frameworks to respond to these challenges. The National Biodiversity Strategy and Action Plan 2025–2030 aligns national priorities with the Kunming-Montreal Global Biodiversity Framework and emphasizes biodiversity mainstreaming, territorial planning, sustainable use, bioeconomy, participation, knowledge generation, monitoring, and biodiversity finance (MAE, 2025). National frameworks such as the National Adaptation Plan, Nationally Determined Contributions, REDD+ Action Plan, Plan Nacional de Desarrollo 2025–2029, territorial planning instruments, and sectoral policies provide additional entry points for integrating biodiversity and climate resilience into development planning (MAE, 2016; MAATE, 2025; SNP, 2025). However, the existence of these frameworks has not yet translated into sufficiently coordinated, financed, and operational implementation in the project landscapes. Subnational authorities and local actors continue to face capacity, coordination, information, and financial constraints to apply

Official Use Only Page 12 of 40





biodiversity and climate priorities in territorial planning, productive systems, and investment decisions.
```

### Passage Bfae90

```text
#### A. PROJECT RATIONALE

Briefly describe the current situation: the global environmental problems and/or climate vulnerabilities that the project will address, the key elements of the system, and underlying drivers of environmental change in the project context, such as population growth, economic development, climate change, sociocultural and political factors, including conflicts, or technological changes. Describe the objective of the project, and the justification for it. (Approximately 3-5 pages) see guidance here

5. Ecuador is one of the world’s most megadiverse countries, hosting an exceptional concentration of species, ecosystems, and genetic resources across terrestrial, freshwater, coastal, and marine environments (Ministerio del Ambiente - MAE, 2016; Ministerio de Ambiente y Energía - MAE, 2025). Its biodiversity underpins essential ecosystem services, including water regulation, soil fertility, carbon sequestration, climate regulation, pollination, food provision, cultural values, and disaster risk reduction, which are fundamental for rural livelihoods, territorial development, and national economic stability (MAE, 2016; MAE, 2025). The country’s constitutional recognition of the rights of nature, its National Protected Areas System (SNAP), Protective Forests and Vegetation (PFV), Areas of

Official Use Only Page 11 of 40
```

### Passage B93372

```text
8. Ecuador has established robust policy and institutional frameworks to respond to these challenges. The National Biodiversity Strategy and Action Plan 2025–2030 aligns national priorities with the Kunming-Montreal Global Biodiversity Framework and emphasizes biodiversity mainstreaming, territorial planning, sustainable use, bioeconomy, participation, knowledge generation, monitoring, and biodiversity finance (MAE, 2025). National frameworks such as the National Adaptation Plan, Nationally Determined Contributions, REDD+ Action Plan, Plan Nacional de Desarrollo 2025–2029, territorial planning instruments, and sectoral policies provide additional entry points for integrating biodiversity and climate resilience into development planning (MAE, 2016; MAATE, 2025; SNP, 2025). However, the existence of these frameworks has not yet translated into sufficiently coordinated, financed, and operational implementation in the project landscapes. Subnational authorities and local actors continue to face capacity, coordination, information, and financial constraints to apply

biodiversity and climate priorities in territorial planning, productive systems, and investment decisions.
```

## Question: How will the project improve public schools in Karnataka?

### Passage Bbc317

```text
#### Project Objective

To improve the management effectiveness and conservation status of Boumba Bek National Park (238,255 ha) and its periphery by reducing key threats to wildlife — particularly the Critically Endangered forest elephant — through IP&LC-led inclusive governance, participatory biomonitoring, and climate-resilient livelihood support, directly benefiting at least 3,000 people (of whom at least 50% women) over the five-year project period.
```

### Passage Bd3a4f

```text
##### **Project description**

This section asks for a theory of change as part of a joined-up description of the project as a whole. The project description is expected to cover the key elements of good project design in an integrated way. It is also expected to meet the GEF’s policy requirements on gender, stakeholders, private sector, and knowledge management and learning (see section D). This section should be a narrative that reads like a joined-up story and not independent elements that answer the guiding questions contained in the PIF guidance document. (Approximately 3-5 pages) see guidance here

**Project Objective** is to improve the management effectiveness and conservation status of Boumba Bek National Park (238,255 ha) and its periphery by reducing key threats to wildlife — particularly the Critically Endangered forest elephant — through IP&LC-led inclusive governance, participatory biomonitoring, and

Official Use Only Page 12 of 31





##### climate-resilient livelihood support, directly benefiting at least 3,000 people (of whom at least 50% women) over the five-year project period.
```

### Passage B3e184

```text
##### B. PROJECT DESCRIPTION

##### **Project description**

This section asks for a theory of change as part of a joined-up description of the project as a whole. The project description is expected to cover the key elements of good project design in an integrated way. It is also expected to meet the GEF’s policy requirements on gender, stakeholders, private sector, and knowledge management and learning (see section D). This section should be a narrative that reads like a joined-up story and not independent elements that answer the guiding questions contained in the PIF guidance document. (Approximately 3-5 pages) see guidance here

**Project Objective** is to improve the management effectiveness and conservation status of Boumba Bek National Park (238,255 ha) and its periphery by reducing key threats to wildlife — particularly the Critically Endangered forest elephant — through IP&LC-led inclusive governance, participatory biomonitoring, and

##### climate-resilient livelihood support, directly benefiting at least 3,000 people (of whom at least 50% women) over the five-year project period.
```

### Passage B5bc4c

```text
GIVEN: Biodiversity loss, ecosystem degradation, climate vulnerability, fragmented governance, weak subnational operationalization of the NBSAP, limited biodiversity finance, weak market integration, and socio- economic vulnerability in the Tropical Dry Forest and Southeastern Ridges landscapes.; IF: The project strengthens governance and SBSAPs; conducts ecosystem risk analyses; improves biodiversity monitoring; promotes biodiversity- positive production systems and value chains; mobilizes investment through financial mechanisms; and reinforces knowledge management, gender- responsive participation, stakeholder engagement, and policy coherence.; THEN: Biodiversity priorities are mainstreamed into territorial planning and investment decisions; producers, MSMEs and local actors adopt sustainable practices; biodiversity-positive finance is mobilized; ecosystem integrity and connectivity are improved; and local capacities for climate resilience and adaptive management are strengthened.; CONTRIBUTING TO: 30,000 ha under improved practices; 808,814 tCO₂e mitigated; 6,000 direct beneficiaries, at least 40% women; reduced pressure on threatened ecosystems and species; strengthened climate resilience; and sustainable, biodiversity-positive livelihoods.
```

### Passage B33ad8

```text
20. These pathways are expected to create reinforcing feedback mechanisms in which improved information supports planning, planning strengthens governance, governance and financing facilitate implementation, and implementation generates environmental and socioeconomic benefits that reinforce stakeholder engagement and institutional ownership. The intervention assumes that key stakeholders maintain active engagement and institutional commitment throughout implementation; that local governments and sectoral actors continue integrating marine–coastal considerations into planning and decision-making processes; that enabling policy and regulatory conditions remain supportive; and that public and private actors demonstrate willingness to participate in financing and implementation mechanisms.

21. The project is designed to strengthen resilience under changing future conditions by institutionalizing planning processes, strengthening local and institutional capacities and establishing adaptive monitoring and learning systems capable of responding to changing environmental, climate and socioeconomic conditions. Rather than relying on isolated interventions, the project seeks to establish mechanisms and capacities capable of maintaining environmental benefits under uncertain future scenarios.

22. By addressing underlying systemic drivers and creating conditions for replication and scaling, the project is expected to contribute to durable global environmental benefits through improved management of approximately 238,973 hectares of marine and coastal ecosystems, improved conservation of critical habitats and strengthened resilience and well-being of coastal communities.

**Figure 2: Theory of Change diagram (Please refer to separate file)**
```

### Passage B927cc

```text
###### **Project Components and Interventions**

The project deploys three mutually reinforcing components.

Component 1 strengthens the governance and inclusion system required for effective protected area management. Although national frameworks reinforce participation of women and IP&LCs, implementation remains weak and platforms are under-resourced. The project therefore reviews and revitalizes existing governance bodies and consultative platforms, establishes clear roles, responsibilities and decision processes, and builds capacities of IP&LCs and authorities to participate effectively, improving coordination across conservation services, councils, civil society organizations and private-sector actors and reducing conflict that undermines conservation outcomes.

To make inclusion operational and credible, the project establishes a functioning grievance redress mechanism covering BBNP and its periphery, with accessible channels for IP&LCs (including women and youth) and transparent case handling. The mechanism is strengthened through assessment and lessons learning, sensitization and training of communities to access it, provision of communications and equipment for effective handling, and capacity building for conservation services on environmental and social management. This reduces grievances related to access, resource use, human–wildlife conflict and enforcement conduct, strengthening trust and enabling sustained co-management.
```

### Passage B2dfe0

```text
### Indicative Project Overview

#### Project Objective

To improve the management effectiveness and conservation status of Boumba Bek National Park (238,255 ha) and its periphery by reducing key threats to wildlife — particularly the Critically Endangered forest elephant — through IP&LC-led inclusive governance, participatory biomonitoring, and climate-resilient livelihood support, directly benefiting at least 3,000 people (of whom at least 50% women) over the five-year project period.
```

### Passage B10cc5

```text
PROJECT DESCRIPTION...........................................................................................................................................................11|
|**Project description**.................................................................................................................................................................11|
|**Coordination and Cooperation with Ongoing Initiatives and Project.**.................................................................................17|
|**Core Indicators**.......................................................................................................................................................................18|
|Key Risks.................................................................................................................................................................................20|
|C. ALIGNMENT WITH GEF-8 PROGRAMMING STRATEGIES AND COUNTRY/REGIONAL PRIORITIES..........................................22|
|D.
```

### Passage B1d2b5

```text
#### Component Balances

|Project Components|GEF Project<br>Financing ($)|Co-financing<br>($)|
|---|---|---|
|Component 1 Improved management effectiveness of BBNP and its periphery through<br>inclusive conservation approaches, increased knowledge, and the participation of the<br>private sector|1,755,385.00|14,888,391.00|

Official Use Only Page 6 of 31





|Component 2 Improved livelihoods and resilience of IP&LCs through access to<br>resources, implementation of benefit sharing mechanisms, and promotion of low-<br>impact agricultural practices|1,296,346.00|11,020,674.00|
|---|---|---|
|Component 3 Communications and knowledge management|132,783.00|1,128,807.00|
|M&E|167,606.00|1,459,603.00|
|**Subtotal**|**3,352,120.00**|**28,497,475.00**|
|Project Management Cost|167,605.00|1,424,892.00|
|**Total Project Cost ($)**|**3,519,725.00**|**29,922,367.00**|

Please provide justification

##### <mark>PROJECT OUTLINE</mark>
```

### Passage Ba2aa0

```text
###### Project Summary

Provide a brief summary description of the project, including: (i) what is the problem and issues to be addressed? (ii) what are the project objectives, and if the project is intended to be transformative, how will this be achieved? iii), how will this be achieved (approach to deliver on objectives), and (iv) what are the GEBs and/or adaptation benefits, and other key expected results. The purpose of the summary is to provide a short, coherent summary for readers. The explanation and justification of the project should be in section B “project description”.(max. 250 words, approximately 1/2 page)

This project will pilot and validate a scalable governance model for inclusive conservation in and around Boumba Bek National Park (BBNP), centered on IP&LC participation, rights operationalization, improved protected area management, and livelihood resilience. BBNP, part of the TRIDOM landscape, is a biodiversity hotspot known for elephants, pangolins, gorillas, and other threatened species. Yet wildlife populations are declining, and between 2011 and 2015 BBNP lost over 75% of its elephants due to poaching, unsustainable hunting, deforestation, and weak protected area management.

The project will apply an integrated and gender-responsive model that combines inclusive governance, biomonitoring, operationalization of access rights, and climate-informed livelihood support. IPLCs, including women, will be trained in biomonitoring of elephants, gorillas and other megafauna in BBNP’s forest clearings, and supported to participate in multistakeholder platforms and decision-making mechanisms. Governance institutions will be reinforced to secure community engagement, while training in low-impact agriculture will reduce deforestation from shifting cultivation and enable farmers to use weather data for climate-resilient practices.

Implemented by MINFOF, the project will improve management effectiveness of 238,255 ha of protected areas, enhance biodiversity-friendly practices on an estimated 23,826 ha of forest area situated in the north and southern peripheries of the national park, maintain viable megafauna populations through permanent monitoring by ecoguards and IPLC teams, and deliver 2.7 million tCO₂-e reductions over 20 years. The project is expected to benefit 3,000 people directly. As an MSP, its primary contribution is catalytic: to generate evidence, institutional learning, and a tested governance model that can be replicated within the TRIDOM landscape and inform larger-scale national investment and policy uptake beyond the project timeframe.

### Indicative Project Overview
```

## Question: How will the project reduce mercury use in artisanal gold mining?

### Passage Bd7c80

```text
##### Project Summary

planetGOLD Mozambique will protect human health and the environment by reducing and, where feasible, eliminating mercury use in Mozambique’s artisanal and small-scale gold mining (ASGM) sector. According to the 2022 Census of Artisanal Miners in Mozambique (CEMAM), there are 483 active artisanal gold mining sites nationwide with approximately 136,160 people involved. ASGM activity and mercury-related risks are concentrated in provinces including Manica, Niassa, Cabo Delgado, Sofala and Tete. The Mozambique National Action Plan for ASGM (NAP) also documents mercury contamination concerns in riverbeds. At the same time, the sector remains characterized by widespread informality, difficult licensing and formalization pathways, and limited access to suitable finance, legal markets and mercury-free technologies.

The project will address these barriers through four integrated components: support for formalization and institutional coordination; improved access to finance and responsible markets; technical solutions and improved practices; and knowledge management and communication. It will help miners and their organizations navigate formalization requirements, strengthen institutional capacity at national and subnational levels, and expand viable pathways for legally compliant, mercury-free gold production.

The project intervention areas will be confirmed during the PPG phase, drawing on the Mozambique NAP, CEMAM and field verification. The project is expected to generate global environmental benefits through reduced mercury use and releases, targeting approximately 1.3 tons of mercury releases avoided (GEF Core Indicator 9). This corresponds to an approximate 80% reduction from an indicative baseline of 1.64 metric tons/year, derived from site-level NAP data and subject to refinement during the PPG phase. In addition, the project is targeting 10,000 direct beneficiaries (35% women).

As a child project under the wider planetGOLD programme, planetGOLD Mozambique will connect to the global coordination project by applying shared methodologies, participating in programme-wide knowledge exchange, contributing lessons learned and communication products, and using common approaches for monitoring, learning, and responsible ASGM market development.
```

### Passage Be1159

```text
#### PROJECT OUTLINE

#### A. PROJECT RATIONALE

Mercury is a toxic chemical with serious impacts on human health and the environment. UNEP’s Global Mercury Assessment identifies the artisanal and small-scale gold mining (ASGM) sector as the largest source of anthropogenic mercury emissions to air globally accounting for about 37%

of the total[1]1 . The sector also produces about 20% of global annual gold output, much of it through largely informal supply chains[2]2 . Mercury released through amalgam burning and other ASGM practices can travel long distances in the atmosphere, be deposited far from the original source, and be transformed into methylmercury in aquatic systems, where it bioaccumulates in fish and wider food webs. Although many miners are aware of the health risks associated with amalgamation, mercury remains widely used because it is one of the easiest and least costly ways to separate gold from ore, while most alternatives require investment in equipment and technical training. Mercury is also readily available in mining areas and is often supplied by buyers and intermediaries in the gold supply chain. As highlighted by the World Health Organization (WHO), these pathways create risks not only for miners and nearby communities, but also for downstream and distant populations exposed through contaminated food and aquatic systems[3]3 .
```

### Passage B935ab

```text
#### A. PROJECT RATIONALE

Briefly describe the current situation: the global environmental problems and/or climate vulnerabilities that the project will address, the key elements of the system, and underlying drivers of environmental change in the project context, such as population growth, economic development, climate change, sociocultural and political factors, including conflicts, or technological changes. Describe the objective of the project, and the justification for it. (Approximately 3-5 pages) see guidance here

Mercury is a toxic chemical with serious impacts on human health and the environment. UNEP’s Global Mercury Assessment identifies the artisanal and small-scale gold mining (ASGM) sector as the largest source of anthropogenic mercury emissions to air globally accounting for about 37%

Official Use Only Page 7 of 49
```

### Passage B45847

```text
#### **Contribution to UNEP’s Programme of Work (PoW) and Mid-Term Strategy (MTS)**

The project is aligned with UNEP’s approved Medium-Term Strategy 2026–2029 and Programme of Work 2026–2027[7]16 ~~.~~ It contributes directly to the strategic objective of moving towards a pollution-free planet by reducing mercury use and releases from artisanal and small-scale gold mining, strengthening national capacity for sound chemicals and waste management, and supporting implementation of the Minamata Convention in Mozambique.

Within the UNEP PoW structure, the project falls primarily under the Chemicals and Pollution Action subprogramme. It also relates, where relevant, to the MTS integrated delivery model through Environmental Law and Governance, Science-Policy, Finance and Economic Transformations, and Digital Transformations in support of formalization, monitoring, access to finance, knowledge management and decision-making.

Expected contributions include stronger national policy and institutional frameworks for ASGM mercury reduction, improved uptake of technical and financial measures that support cleaner production, and measurable reductions in mercury-related pollution risks affecting people, water, soils and ecosystems in priority mining areas. The project will also contribute to stronger engagement by public institutions, local communities, civil society and private-sector actors in pollution prevention and responsible gold supply chains.
```

### Passage Ba2e81

```text
In the absence of sustained structural change, experience from comparable ASGM contexts indicates that key barriers to reducing mercury use are likely to persist. Evidence from previous planetGOLD projects shows that adoption of mercury-free technologies remains limited where miners lack access to finance, technical support and clear economic incentives, while formalization efforts tend to remain slow and fragmented in the absence of tangible benefits such as access to markets and services ~~.~~[9]9 As a result, miners would likely continue to operate within informal systems characterized by limited access to credit, weak integration into responsible supply chains and continued reliance on established but hazardous processing practices. In these conditions, ad hoc support initiatives may address immediate needs but would be unlikely to alter the underlying drivers of informality and mercury use.
```

### Passage B7fa11

```text
#### **Contribution to UNEP’s Programme of Work (PoW) and Mid-Term Strategy (MTS)**

The project is aligned with UNEP’s approved Medium-Term Strategy 2026–2029 and Programme of Work 2026–2027<sup><u>[7]16</u></sup> ~~.~~ It contributes directly to the strategic objective of moving towards a pollution-free planet by reducing mercury use and releases from artisanal and small-scale gold mining, strengthening national capacity for sound chemicals and waste management, and supporting implementation of the Minamata Convention in Mozambique.

Within the UNEP PoW structure, the project falls primarily under the Chemicals and Pollution Action subprogramme. It also relates, where relevant, to the MTS integrated delivery model through Environmental Law and Governance, Science-Policy, Finance and Economic Transformations, and Digital Transformations in support of formalization, monitoring, access to finance, knowledge management and decision-making.

Expected contributions include stronger national policy and institutional frameworks for ASGM mercury reduction, improved uptake of technical and financial measures that support cleaner production, and measurable reductions in mercury-related pollution risks affecting people, water, soils and ecosystems in priority mining areas. The project will also contribute to stronger engagement by public institutions, local communities, civil society and private-sector actors in pollution prevention and responsible gold supply chains.
```

### Passage B2af42

```text
1. Implement actions that guarantee the reduction and/or elimination of mercury use in ASGM.

2. Create a legal and regulatory framework that facilitates ASGM practice and commercialization of mineral resources, while developing and enforcing occupational safety and health standards and a strategic environmental management plan.

3. Strengthen mining associations and cooperatives and intensify ASM formalization through the creation of associations and cooperatives of artisanal miners.

4. Build and strengthen institutional capacity regarding mercury and support capacity-building and institutional alignment of ASM intervening sectors.

5. Intensify awareness on the use of mercury in ASGM and its impacts, and provide information to artisanal and small-scale miners and communities.
```

### Passage B54bfa

```text
#### **Component 3: Technical Solutions and Improved Practices**

Component 3 focuses on technical solutions and improved practices to reduce mercury use and releases, and to lower pollution risks in target ASGM areas, through increased awareness of mercury risks and the uptake of mercury-free technologies and improved processing practices. Mercury use in the country remains underreported given the high level of informality, and the large number of miners identified by the CEMAM census suggests that actual mercury use and associated releases are likely to be higher than currently documented. The component is therefore designed around a practical sequence that moves from risk awareness and technical assessment to demonstration, training, adoption support and follow-up.

Mercury remains widely used because it is familiar, accessible and perceived by miners as an effective low-cost option. The project must therefore demonstrate that mercury-free alternatives can deliver practical, economically viable and locally appropriate improvements in gold recovery and working conditions while also reducing mercury releases and associated pollution risks. Without such evidence, incentives to shift away from mercury-based methods are likely to remain limited.
```

### Passage Bd6c6f

```text
##### Project Summary

Provide a brief summary description of the project, including: (i) what is the problem and issues to be addressed? (ii) what are the project objectives, and if the project is intended to be transformative, how will this be achieved? iii), how will this be achieved (approach to deliver on objectives), and (iv) what are the GEBs and/or adaptation benefits, and other key expected results. The purpose of the summary is to provide a short, coherent summary for readers. The explanation and justification of the project should be in section B “project description”.(max. 250 words, approximately 1/2 page)

planetGOLD Mozambique will protect human health and the environment by reducing and, where feasible, eliminating mercury use in Mozambique’s artisanal and small-scale gold mining (ASGM) sector. According to the 2022 Census of Artisanal Miners in Mozambique (CEMAM), there are 483 active artisanal gold mining sites nationwide with approximately 136,160 people involved. ASGM activity and mercury-related risks are concentrated in provinces including Manica, Niassa, Cabo Delgado, Sofala and Tete. The Mozambique National Action Plan for ASGM (NAP) also documents mercury contamination concerns in riverbeds. At the same time, the sector remains characterized by widespread informality, difficult licensing and formalization pathways, and limited access to suitable finance, legal markets and mercury-free technologies.

The project will address these barriers through four integrated components: support for formalization and institutional coordination; improved access to finance and responsible markets; technical solutions and improved practices; and knowledge management and communication. It will help miners and their organizations navigate formalization requirements, strengthen institutional capacity at national and subnational levels, and expand viable pathways for legally compliant, mercury-free gold production.

The project intervention areas will be confirmed during the PPG phase, drawing on the Mozambique NAP, CEMAM and field verification. The project is expected to generate global environmental benefits through reduced mercury use and releases, targeting approximately 1.3 tons of mercury releases avoided (GEF Core Indicator 9). This corresponds to an approximate 80% reduction from an indicative baseline of 1.64 metric tons/year, derived from site-level NAP data and subject to refinement during the PPG phase. In addition, the project is targeting 10,000 direct beneficiaries (35% women).

As a child project under the wider planetGOLD programme, planetGOLD Mozambique will connect to the global coordination project by applying shared methodologies, participating in programme-wide knowledge exchange, contributing lessons learned and communication products, and using common approaches for monitoring, learning, and responsible ASGM market development.
```

## Question: What marine protected areas are covered in Ecuador?

### Passage B0e3da

```text
#### PROJECT OUTLINE

#### A. PROJECT RATIONALE

###### **Current situation and environmental context**

1. Ecuador’s marine and coastal ecosystems are globally significant due to their high biodiversity, ecological connectivity and provision of ecosystem services that sustain livelihoods, productive sectors and climate resilience. Ecuador's continental coastline is part of the Eastern Tropical Pacific, one of the most productive and diverse marine regions on the planet. The country has a coastline of approximately 5,271 km, which extends across the five coastal provinces of Ecuador (Esmeraldas, Manabí, Santa Elena, Guayas and El Oro) and in more than 20 Decentralized Autonomous Governments (GADs) and is part of the National Marine-Coastal Area, whose total area amounts to 1,367,188 km², including inland waters, territorial sea and exclusive economic

zon ~~e~~[1]1 ~~.~~ These ecosystems—mangroves, beaches, estuaries, wetlands, and shallow seabeds—sustain rich biodiversity and provide essential services such as coastal protection, fishery resources, climate mitigation, and support for tourism and commercial activities.
```

### Passage B5dae7

```text
###### **Baseline situation and existing investments**

5. Ecuador has developed an important policy and institutional basis for integrated coastal management over recent decades. The country was an early regional leader in Integrated Coastal Zone Management (ICZM), and more recently the Organic Environmental Code (COA) and its regulations (RCOA) established requirements for marine–coastal planning instruments, including Integrated Marine Coastal Management Plans and Beach and Adjacent Coastal Strip Management Plans.

6. The baseline scenario includes multiple ongoing public and donor-supported initiatives addressing marine biodiversity conservation, coastal management, sustainable finance and territorial planning. These include national investments and complementary initiatives such as BIOFIN and broader biodiversity and coastal management interventions aimed at strengthening financing mechanisms and sustainable management approaches.
```

### Passage B16835

```text
###### **Strategic fit:**

Official Use Only Page 11 of 37





14. The project builds on existing national and international investments and lessons learned from previous coastal and marine management experiences in Ecuador and the region. It complements ongoing biodiversity and financing initiatives while addressing gaps related to institutional capacity, coordination and implementation.

15. The project contributes directly to national priorities related to biodiversity conservation, territorial planning and climate resilience, while supporting implementation of international commitments under the Kunming–Montreal Global Biodiversity Framework, particularly Targets 1, 2 and 10 related to integrated spatial planning, ecosystem restoration and sustainable management.

16. The GEF incremental value lies in enabling Ecuador to transition from fragmented project-based interventions toward an operational, participatory and financially sustainable national system for integrated marine–coastal management capable of sustaining biodiversity outcomes and resilience over the long term.

<u>[1]</u> Ministerio del Ambiente (MAE). 2017. Plan de Ordenamiento del Espacio Marino Costero del Ecuador (POEMC) 2017–2030. Quito: MAE.

- <u>[2]</u> MAE. 2017

<u>[3]</u> Ministerio del Ambiente, Agua y Transición Ecológica (MAATE). 2023. Plan Nacional de Adaptación al Cambio Climático 2023–2027. Quito: MAATE.

<u>[4]</u> Banco Mundial. 2024. Informe sobre el Clima y el Desarrollo del País: Ecuador (CCDR). Washington, DC: Banco Mundial.

<u>[5]</u> Vásconez, M. 2025. Evaluación de la capacidad de gestión institucional de los GAD para la implementación del Manejo Costero Integrado. Documento interno. Quito: Conservación Internacional Ecuador (CI).

#### B. PROJECT DESCRIPTION
```

### Passage B7f5c1

```text
#### PROJECT OUTLINE

#### A. PROJECT RATIONALE

5. Ecuador is one of the world’s most megadiverse countries, hosting an exceptional concentration of species, ecosystems, and genetic resources across terrestrial, freshwater, coastal, and marine environments (Ministerio del Ambiente - MAE, 2016; Ministerio de Ambiente y Energía - MAE, 2025). Its biodiversity underpins essential ecosystem services, including water regulation, soil fertility, carbon sequestration, climate regulation, pollination, food provision, cultural values, and disaster risk reduction, which are fundamental for rural livelihoods, territorial development, and national economic stability (MAE, 2016; MAE, 2025). The country’s constitutional recognition of the rights of nature, its National Protected Areas System (SNAP), Protective Forests and Vegetation (PFV), Areas of

Conservation and Sustainable Use (ACUS), Other Effective Area-Based Conservation Measures (OECMs), and biodiversity-related planning frameworks provide a strong enabling foundation for conservation and sustainable use. Nevertheless, biodiversity continues to face increasing pressure from land-use change, deforestation, ecosystem degradation, unsustainable agricultural and livestock expansion, mining and other extractive activities, forest fires, pollution, and limited integration of biodiversity values into productive and financial systems (MAE, 2017; MAATE, 2025a; MAE, 2025).
```

### Passage Bab2bd

```text
###### **Current situation and environmental context**

1. Ecuador’s marine and coastal ecosystems are globally significant due to their high biodiversity, ecological connectivity and provision of ecosystem services that sustain livelihoods, productive sectors and climate resilience. Ecuador's continental coastline is part of the Eastern Tropical Pacific, one of the most productive and diverse marine regions on the planet. The country has a coastline of approximately 5,271 km, which extends across the five coastal provinces of Ecuador (Esmeraldas, Manabí, Santa Elena, Guayas and El Oro) and in more than 20 Decentralized Autonomous Governments (GADs) and is part of the National Marine-Coastal Area, whose total area amounts to 1,367,188 km², including inland waters, territorial sea and exclusive economic

Official Use Only Page 7 of 37





zon ~~e~~<sup><u>[1]</u>1</sup> ~~.~~ These ecosystems—mangroves, beaches, estuaries, wetlands, and shallow seabeds—sustain rich biodiversity and provide essential services such as coastal protection, fishery resources, climate mitigation, and support for tourism and commercial activities.

**Figure 1:** Project implementation area (Please refer to separate file)

2. However, these ecosystems are increasingly exposed to cumulative pressures generated by anthropogenic and climate-related drivers. The Coastal Marine Space Management Plan (POEMC, 2017–2030) identifies 29 types of coastal ecosystems recognized
```

### Passage B20ebe

```text
##### Project Title

Integrated marine coastal management for biodiversity conservation in the coasts and beaches of Ecuador

|Region|GEF Project ID|
|---|---|
|Latin America and the Caribbean|12365|
|Country(ies)|Type of Project|
|Ecuador|MSP|
|GEF Agency(ies):|GEF Agency ID|
|UNDP|10314|
|Executing Partner|Executing Partner Type|
|Conservation International (CI)|CSO|
|GEF Focal Area (s)|Submission Date|
|Biodiversity|6/1/2026|
|Project Sector (CCM Only)||
```

### Passage B9ab5c

```text
24. The Tropical Dry Forest landscape, located in Manabí and Santa Elena, represents one of the most threatened and fragmented dry forest systems in Ecuador and the wider Tumbesian region. It hosts specialized and endemic species adapted to seasonal water stress and includes ecological subtypes that provide critical ecosystem services for rural livelihoods, water regulation, soil stability, and climate resilience. However, this landscape is under severe pressure from deforestation, agricultural and livestock expansion, forest fires, land degradation, and unsustainable land-use practices. Climate change compounds these pressures through prolonged droughts, heatwaves, erratic rainfall, and increased fire risk, reducing ecosystem functionality and agricultural productivity. Despite these threats, the landscape offers significant opportunities for ecological restoration, sustainable land management, biodiversity-based businesses, and community-based conservation, particularly where producer organizations, local governments, and community structures are already active.

Official Use Only Page 17 of 40
```

### Passage Bc1787

```text
3. WWF Ecuador.
```

### Passage B6cf6e

```text
##### Project Summary

The project will strengthen integrated marine–coastal management for biodiversity conservation along Ecuador’s coastline through improved territorial planning, governance mechanisms, and implementation of priority conservation actions. Covering Ecuador’s five coastal provinces (Esmeraldas, Manabí, Santa Elena, Guayas and El Oro), the project addresses biodiversity loss driven by unsustainable coastal and marine use practices, habitat degradation, and fragmented governance systems. The project contributes to GEF-8 Biodiversity objectives and supports implementation of the Kunming–Montreal Global Biodiversity Framework through integrated seascape management approaches and strengthened enabling conditions for biodiversity conservation.

The project will strengthen institutional and technical capacities for participatory marine–coastal planning, support implementation of Integrated Marine Coastal Management Plans (IMCM) and Marine Beaches and Adjacent Strips Management Plans (MBASMP) and establish sustainable financing mechanisms and knowledge systems for long-term implementation. The project will directly support interventions across approximately 50% of Ecuador’s coastal municipalities with marine beaches and coastal strips while establishing scalable governance, planning and financing approaches designed for replication beyond project intervention areas. Interventions are expected to improve management of approximately **60,312 ha of coastal ecosystems (GEF CI 4.1)** and **178,661 ha of marine habitat (GEF CI 5)** and directly benefit approximately **1,118,773 people (GEF CI 11)** across local communities and coastal populations, while improving ecological connectivity, ecosystem resilience and biodiversity conservation outcomes, including strengthened ecosystem services and ecosystem-based approaches that support adaptation and resilience of coastal socio-ecological systems. Through strengthened governance systems, sustainable financing mechanisms and adaptive knowledge systems, the intervention seeks to generate durable global environmental benefits extending beyond direct intervention sites.

## Indicative Project Overview

### Project Objective

Improved ecosystem and critical habitats conservation, restoration and resilience, and improved welfare of local communities in marine and coastal areas of Ecuador
```

## Question: What threats do Ecuador's coastal and marine ecosystems face?

### Passage Bce4a8

```text
Map 1. National system of protected areas; protective forest and vegetation and key biodiversity areas in Tropical Dry Forest - Southeastern Ridges.

24. The Tropical Dry Forest landscape, located in Manabí and Santa Elena, represents one of the most threatened and fragmented dry forest systems in Ecuador and the wider Tumbesian region. It hosts specialized and endemic species adapted to seasonal water stress and includes ecological subtypes that provide critical ecosystem services for rural livelihoods, water regulation, soil stability, and climate resilience. However, this landscape is under severe pressure from deforestation, agricultural and livestock expansion, forest fires, land degradation, and unsustainable land-use practices. Climate change compounds these pressures through prolonged droughts, heatwaves, erratic rainfall, and increased fire risk, reducing ecosystem functionality and agricultural productivity. Despite these threats, the landscape offers significant opportunities for ecological restoration, sustainable land management, biodiversity-based businesses, and community-based conservation, particularly where producer organizations, local governments, and community structures are already active.
```

### Passage B5108b

```text
#### A. PROJECT RATIONALE

Briefly describe the current situation: the global environmental problems and/or climate vulnerabilities that the project will address, the key elements of the system, and underlying drivers of environmental change in the project context, such as population growth, economic development, climate change, sociocultural and political factors, including conflicts, or technological changes. Describe the objective of the project, and the justification for it. (Approximately 3-5 pages) see guidance here

5. Ecuador is one of the world’s most megadiverse countries, hosting an exceptional concentration of species, ecosystems, and genetic resources across terrestrial, freshwater, coastal, and marine environments (Ministerio del Ambiente - MAE, 2016; Ministerio de Ambiente y Energía - MAE, 2025). Its biodiversity underpins essential ecosystem services, including water regulation, soil fertility, carbon sequestration, climate regulation, pollination, food provision, cultural values, and disaster risk reduction, which are fundamental for rural livelihoods, territorial development, and national economic stability (MAE, 2016; MAE, 2025). The country’s constitutional recognition of the rights of nature, its National Protected Areas System (SNAP), Protective Forests and Vegetation (PFV), Areas of

Official Use Only Page 11 of 40
```

### Passage B4f5ff

```text
#### PROJECT OUTLINE

#### A. PROJECT RATIONALE

###### **Current situation and environmental context**

1. Ecuador’s marine and coastal ecosystems are globally significant due to their high biodiversity, ecological connectivity and provision of ecosystem services that sustain livelihoods, productive sectors and climate resilience. Ecuador's continental coastline is part of the Eastern Tropical Pacific, one of the most productive and diverse marine regions on the planet. The country has a coastline of approximately 5,271 km, which extends across the five coastal provinces of Ecuador (Esmeraldas, Manabí, Santa Elena, Guayas and El Oro) and in more than 20 Decentralized Autonomous Governments (GADs) and is part of the National Marine-Coastal Area, whose total area amounts to 1,367,188 km², including inland waters, territorial sea and exclusive economic

zon ~~e~~[1]1 ~~.~~ These ecosystems—mangroves, beaches, estuaries, wetlands, and shallow seabeds—sustain rich biodiversity and provide essential services such as coastal protection, fishery resources, climate mitigation, and support for tourism and commercial activities.
```

### Passage Bf1b27

```text
##### Project Summary

The project will strengthen integrated marine–coastal management for biodiversity conservation along Ecuador’s coastline through improved territorial planning, governance mechanisms, and implementation of priority conservation actions. Covering Ecuador’s five coastal provinces (Esmeraldas, Manabí, Santa Elena, Guayas and El Oro), the project addresses biodiversity loss driven by unsustainable coastal and marine use practices, habitat degradation, and fragmented governance systems. The project contributes to GEF-8 Biodiversity objectives and supports implementation of the Kunming–Montreal Global Biodiversity Framework through integrated seascape management approaches and strengthened enabling conditions for biodiversity conservation.

The project will strengthen institutional and technical capacities for participatory marine–coastal planning, support implementation of Integrated Marine Coastal Management Plans (IMCM) and Marine Beaches and Adjacent Strips Management Plans (MBASMP) and establish sustainable financing mechanisms and knowledge systems for long-term implementation. The project will directly support interventions across approximately 50% of Ecuador’s coastal municipalities with marine beaches and coastal strips while establishing scalable governance, planning and financing approaches designed for replication beyond project intervention areas. Interventions are expected to improve management of approximately **60,312 ha of coastal ecosystems (GEF CI 4.1)** and **178,661 ha of marine habitat (GEF CI 5)** and directly benefit approximately **1,118,773 people (GEF CI 11)** across local communities and coastal populations, while improving ecological connectivity, ecosystem resilience and biodiversity conservation outcomes, including strengthened ecosystem services and ecosystem-based approaches that support adaptation and resilience of coastal socio-ecological systems. Through strengthened governance systems, sustainable financing mechanisms and adaptive knowledge systems, the intervention seeks to generate durable global environmental benefits extending beyond direct intervention sites.

## Indicative Project Overview

### Project Objective

Improved ecosystem and critical habitats conservation, restoration and resilience, and improved welfare of local communities in marine and coastal areas of Ecuador
```

### Passage B3d03e

```text
###### **Baseline situation and existing investments**

5. Ecuador has developed an important policy and institutional basis for integrated coastal management over recent decades. The country was an early regional leader in Integrated Coastal Zone Management (ICZM), and more recently the Organic Environmental Code (COA) and its regulations (RCOA) established requirements for marine–coastal planning instruments, including Integrated Marine Coastal Management Plans and Beach and Adjacent Coastal Strip Management Plans.

6. The baseline scenario includes multiple ongoing public and donor-supported initiatives addressing marine biodiversity conservation, coastal management, sustainable finance and territorial planning. These include national investments and complementary initiatives such as BIOFIN and broader biodiversity and coastal management interventions aimed at strengthening financing mechanisms and sustainable management approaches.
```

### Passage B41750

```text
###### **Current situation and environmental context**

1. Ecuador’s marine and coastal ecosystems are globally significant due to their high biodiversity, ecological connectivity and provision of ecosystem services that sustain livelihoods, productive sectors and climate resilience. Ecuador's continental coastline is part of the Eastern Tropical Pacific, one of the most productive and diverse marine regions on the planet. The country has a coastline of approximately 5,271 km, which extends across the five coastal provinces of Ecuador (Esmeraldas, Manabí, Santa Elena, Guayas and El Oro) and in more than 20 Decentralized Autonomous Governments (GADs) and is part of the National Marine-Coastal Area, whose total area amounts to 1,367,188 km², including inland waters, territorial sea and exclusive economic

Official Use Only Page 7 of 37





zon ~~e~~<sup><u>[1]</u>1</sup> ~~.~~ These ecosystems—mangroves, beaches, estuaries, wetlands, and shallow seabeds—sustain rich biodiversity and provide essential services such as coastal protection, fishery resources, climate mitigation, and support for tourism and commercial activities.

**Figure 1:** Project implementation area (Please refer to separate file)

2. However, these ecosystems are increasingly exposed to cumulative pressures generated by anthropogenic and climate-related drivers. The Coastal Marine Space Management Plan (POEMC, 2017–2030) identifies 29 types of coastal ecosystems recognized
```

### Passage B3a1fe

```text
#### PROJECT OUTLINE

#### A. PROJECT RATIONALE

5. Ecuador is one of the world’s most megadiverse countries, hosting an exceptional concentration of species, ecosystems, and genetic resources across terrestrial, freshwater, coastal, and marine environments (Ministerio del Ambiente - MAE, 2016; Ministerio de Ambiente y Energía - MAE, 2025). Its biodiversity underpins essential ecosystem services, including water regulation, soil fertility, carbon sequestration, climate regulation, pollination, food provision, cultural values, and disaster risk reduction, which are fundamental for rural livelihoods, territorial development, and national economic stability (MAE, 2016; MAE, 2025). The country’s constitutional recognition of the rights of nature, its National Protected Areas System (SNAP), Protective Forests and Vegetation (PFV), Areas of

Conservation and Sustainable Use (ACUS), Other Effective Area-Based Conservation Measures (OECMs), and biodiversity-related planning frameworks provide a strong enabling foundation for conservation and sustainable use. Nevertheless, biodiversity continues to face increasing pressure from land-use change, deforestation, ecosystem degradation, unsustainable agricultural and livestock expansion, mining and other extractive activities, forest fires, pollution, and limited integration of biodiversity values into productive and financial systems (MAE, 2017; MAATE, 2025a; MAE, 2025).
```

### Passage B9364b

```text
24. The Tropical Dry Forest landscape, located in Manabí and Santa Elena, represents one of the most threatened and fragmented dry forest systems in Ecuador and the wider Tumbesian region. It hosts specialized and endemic species adapted to seasonal water stress and includes ecological subtypes that provide critical ecosystem services for rural livelihoods, water regulation, soil stability, and climate resilience. However, this landscape is under severe pressure from deforestation, agricultural and livestock expansion, forest fires, land degradation, and unsustainable land-use practices. Climate change compounds these pressures through prolonged droughts, heatwaves, erratic rainfall, and increased fire risk, reducing ecosystem functionality and agricultural productivity. Despite these threats, the landscape offers significant opportunities for ecological restoration, sustainable land management, biodiversity-based businesses, and community-based conservation, particularly where producer organizations, local governments, and community structures are already active.

Official Use Only Page 17 of 40
```

### Passage B747dd

```text
6. The global environmental problem addressed by the project is the continued loss, fragmentation, and degradation of biodiversity-rich landscapes that are critical for maintaining ecosystem integrity, ecological connectivity, threatened species habitats, and climate resilience. These pressures are particularly acute in the Ecuadorian Dry Forest landscape of Manabí and Santa Elena and the Southeastern Ridges landscape of Loja and Zamora Chinchipe. The Ecuadorian Dry Forest represents one of the most threatened and fragmented ecosystems in the country and the wider Tumbesian region, with high levels of endemism, strong ecological specialization, and severe exposure to drought, heatwaves, forest fires, and land conversion (IUCN, 2020; MAATE, 2025b). The Southeastern Ridges constitute a complex biogeographic transition zone connecting Andean, Amazonian, montane forest, cloud forest, páramo, and dry forest systems, supporting high biodiversity and ecological connectivity while facing increasing pressures from deforestation, mining, agricultural expansion, and rural socioeconomic change (MAE, 2016; MAATE, 2025b). Together, these landscapes include Key Biodiversity Areas (KBAs), protected areas, PFV, ACUS and other conservation and management mechanisms that are essential to maintain ecosystem functionality and reduce extinction risks.
```

## Question: What are the main components of the planetGOLD project in Mozambique?

### Passage B31e76

```text
##### Project Summary

planetGOLD Mozambique will protect human health and the environment by reducing and, where feasible, eliminating mercury use in Mozambique’s artisanal and small-scale gold mining (ASGM) sector. According to the 2022 Census of Artisanal Miners in Mozambique (CEMAM), there are 483 active artisanal gold mining sites nationwide with approximately 136,160 people involved. ASGM activity and mercury-related risks are concentrated in provinces including Manica, Niassa, Cabo Delgado, Sofala and Tete. The Mozambique National Action Plan for ASGM (NAP) also documents mercury contamination concerns in riverbeds. At the same time, the sector remains characterized by widespread informality, difficult licensing and formalization pathways, and limited access to suitable finance, legal markets and mercury-free technologies.

The project will address these barriers through four integrated components: support for formalization and institutional coordination; improved access to finance and responsible markets; technical solutions and improved practices; and knowledge management and communication. It will help miners and their organizations navigate formalization requirements, strengthen institutional capacity at national and subnational levels, and expand viable pathways for legally compliant, mercury-free gold production.

The project intervention areas will be confirmed during the PPG phase, drawing on the Mozambique NAP, CEMAM and field verification. The project is expected to generate global environmental benefits through reduced mercury use and releases, targeting approximately 1.3 tons of mercury releases avoided (GEF Core Indicator 9). This corresponds to an approximate 80% reduction from an indicative baseline of 1.64 metric tons/year, derived from site-level NAP data and subject to refinement during the PPG phase. In addition, the project is targeting 10,000 direct beneficiaries (35% women).

As a child project under the wider planetGOLD programme, planetGOLD Mozambique will connect to the global coordination project by applying shared methodologies, participating in programme-wide knowledge exchange, contributing lessons learned and communication products, and using common approaches for monitoring, learning, and responsible ASGM market development.
```

### Passage B72602

```text
#### **Contribution to National Strategies**

At the country level, the project is aligned with Mozambique’s commitments under the Minamata Convention on Mercury and with the National Action Plan (NAP)[3]12 for the ASGM sector by taking forward its policy recommendations through implementation support for formalization and technology transfer. Close coordination will be maintained with relevant government bodies, including the Ministry of Agriculture, Environment and Fisheries (MAAP) and the Ministry of Mineral Resources and Energy (MIREME), to ensure alignment with national minerals policy and environmental regulations.

During the PIF development process, the Mozambican authorities across relevant ministries were consulted to ensure that the project’s approach was in line with the ministry’s strategies, particularly the national ASGM formalization strategy.

Notably, the planetGOLD Mozambique project will contribute to the following national priorities:
```

### Passage B57442

```text
#### **Coordination and Cooperation with Ongoing Initiatives and Project.**

Does the GEF Agency expect to play an execution role on this project?

If so, please describe that role here. Also, please add a short explanation to describe cooperation with ongoing initiatives and projects, including potential for co-location and/or sharing of expertise/staffing

The planetGOLD programme is a key global initiative for advancing systemic change in the ASGM sector by supporting safer, cleaner and more responsible gold production. It recognizes that reducing and, where feasible, eliminating mercury use in ASGM requires an integrated approach that addresses the underlying drivers of mercury dependence and the barriers that prevent miners from transitioning to mercury-free technologies and more formalized business models. These include formalization, access to finance, responsible gold supply chains, awareness of mercuryrelated health and environmental risks, access to mercury-free technologies, and strengthened local capacity for longer-term sustainability.

planetGOLD Mozambique is expected to complement previous GEF-funded and bilateral efforts on ASGM mercury reduction and formalization. At the global level, the programme supports implementation of the Minamata Convention on Mercury and related national commitments, including Mozambique’s National Action Plan on ASGM.
```

### Passage B5f16b

```text
## Indicative Project Overview

Project Objective

Official Use Only Page 4 of 49





To protect human health and the environment by reducing mercury use in Mozambique’s ASGM sector, and contributing to and learning from the planetGOLD Global Programme

#### <mark>Project Components</mark>
```

### Passage B520c3

```text
#### **Contribution to National Strategies**

At the country level, the project is aligned with Mozambique’s commitments under the Minamata Convention on Mercury and with the National Action Plan (NAP)[3]<sup>12</sup> for the ASGM sector by taking forward its policy recommendations through implementation support for formalization and technology transfer. Close coordination will be maintained with relevant government bodies, including the Ministry of Agriculture, Environment and Fisheries (MAAP) and the Ministry of Mineral Resources and Energy (MIREME), to ensure alignment with national minerals policy and environmental regulations.

During the PIF development process, the Mozambican authorities across relevant ministries were consulted to ensure that the project’s approach was in line with the ministry’s strategies, particularly the national ASGM formalization strategy.

Notably, the planetGOLD Mozambique project will contribute to the following national priorities:

Official Use Only Page 39 of 49
```

### Passage Bdd7d7

```text
##### Project Title

Global Opportunities for the Long-Term Development of the Artisanal and Small-Scale Gold Mining Sector in Mozambique – planetGOLD Mozambique

|Region|GEF Project ID|
|---|---|
|Africa|12368|
|Country(ies)|Type of Project|
|Mozambique|MSP|
|GEF Agency(ies):|GEF Agency ID|
|UNEP|273890|
|Executing Partner|Executing Partner Type|
|The Impact Facility|CSO|
|GEF Focal Area (s)|Submission Date|
|Chemicals and Waste|6/8/2026|
|Project Sector (CCM Only)||
```

### Passage B89ae2

```text
#### **Coordination and Cooperation with Ongoing Initiatives and Project.**

Does the GEF Agency expect to play an execution role on this project?

The planetGOLD programme is a key global initiative for advancing systemic change in the ASGM sector by supporting safer, cleaner and more responsible gold production. It recognizes that reducing and, where feasible, eliminating mercury use in ASGM requires an integrated approach that addresses the underlying drivers of mercury dependence and the barriers that prevent miners from transitioning to mercury-free technologies and more formalized business models. These include formalization, access to finance, responsible gold supply chains, awareness of mercuryrelated health and environmental risks, access to mercury-free technologies, and strengthened local capacity for longer-term sustainability.

planetGOLD Mozambique is expected to complement previous GEF-funded and bilateral efforts on ASGM mercury reduction and formalization. At the global level, the programme supports implementation of the Minamata Convention on Mercury and related national commitments, including Mozambique’s National Action Plan on ASGM.
```

### Passage Bc61b6

```text
##### Project Summary

Provide a brief summary description of the project, including: (i) what is the problem and issues to be addressed? (ii) what are the project objectives, and if the project is intended to be transformative, how will this be achieved? iii), how will this be achieved (approach to deliver on objectives), and (iv) what are the GEBs and/or adaptation benefits, and other key expected results. The purpose of the summary is to provide a short, coherent summary for readers. The explanation and justification of the project should be in section B “project description”.(max. 250 words, approximately 1/2 page)

planetGOLD Mozambique will protect human health and the environment by reducing and, where feasible, eliminating mercury use in Mozambique’s artisanal and small-scale gold mining (ASGM) sector. According to the 2022 Census of Artisanal Miners in Mozambique (CEMAM), there are 483 active artisanal gold mining sites nationwide with approximately 136,160 people involved. ASGM activity and mercury-related risks are concentrated in provinces including Manica, Niassa, Cabo Delgado, Sofala and Tete. The Mozambique National Action Plan for ASGM (NAP) also documents mercury contamination concerns in riverbeds. At the same time, the sector remains characterized by widespread informality, difficult licensing and formalization pathways, and limited access to suitable finance, legal markets and mercury-free technologies.

The project will address these barriers through four integrated components: support for formalization and institutional coordination; improved access to finance and responsible markets; technical solutions and improved practices; and knowledge management and communication. It will help miners and their organizations navigate formalization requirements, strengthen institutional capacity at national and subnational levels, and expand viable pathways for legally compliant, mercury-free gold production.

The project intervention areas will be confirmed during the PPG phase, drawing on the Mozambique NAP, CEMAM and field verification. The project is expected to generate global environmental benefits through reduced mercury use and releases, targeting approximately 1.3 tons of mercury releases avoided (GEF Core Indicator 9). This corresponds to an approximate 80% reduction from an indicative baseline of 1.64 metric tons/year, derived from site-level NAP data and subject to refinement during the PPG phase. In addition, the project is targeting 10,000 direct beneficiaries (35% women).

As a child project under the wider planetGOLD programme, planetGOLD Mozambique will connect to the global coordination project by applying shared methodologies, participating in programme-wide knowledge exchange, contributing lessons learned and communication products, and using common approaches for monitoring, learning, and responsible ASGM market development.
```

### Passage B6e2fd

```text
General Project Information

##### Project Title

Global Opportunities for the Long-Term Development of the Artisanal and Small-Scale Gold Mining Sector in Mozambique – planetGOLD Mozambique

Region: Africa; GEF Project ID: 12368
Region: Country(ies); GEF Project ID: Type of Project
Region: Mozambique; GEF Project ID: MSP
Region: GEF Agency(ies):; GEF Project ID: GEF Agency ID
Region: UNEP; GEF Project ID: 273890
Region: Executing Partner; GEF Project ID: Executing Partner Type
Region: The Impact Facility; GEF Project ID: CSO
Region: GEF Focal Area (s); GEF Project ID: Submission Date
Region: Chemicals and Waste; GEF Project ID: 6/8/2026
Region: Project Sector (CCM Only)
```

### Passage B7763f

```text
## Indicative Project Overview

Project Objective

To protect human health and the environment by reducing mercury use in Mozambique’s ASGM sector, and contributing to and learning from the planetGOLD Global Programme

#### Project Components

### Component 1: Enhancing the Formalization of the ASGM Sector

Component Type: Technical Assistance; Trust Fund: GET
Component Type: GEF Project Financing ($); Trust Fund: Co-financing ($)
Component Type: 942,857.00; Trust Fund: 6,477,163.00

Outcome:

Outcome 1: Government, stakeholders and miners strengthen formalization capacity and support development and implementation of policy and regulatory measures for responsible ASGM, including gender- and youthresponsive measures.
```

## Question: What is the total GEF financing requested?

### Passage Bb87a6

```text
#### **GEF Financing Table**

**Indicative Trust Fund Resources Requested by Agency(ies), Country(ies), Focal Area and the Programming of Funds**

GEF Agency: UNIDO; Trust Fund: SCCF- A; Country/ Regional/ Global: Cuba; Focal Area: Climate Change; Programming of Funds: SCCF-A Country allocation; Grant / Non- Grant: Grant; GEF Project Grant($): 2,639,726.00; Agency Fee($): 250,774.00; Total GEF Financing($): 2,890,500.00
GEF Agency: Total GEF; Trust Fund: Resourc; Country/ Regional/ Global: es ($); GEF Project Grant($): 2,639,726.00; Agency Fee($): 250,774.00; Total GEF Financing($): 2,890,500.00
```

### Passage Ba6635

```text
#### **GEF Financing Table**

**Indicative Trust Fund Resources Requested by Agency(ies), Country(ies), Focal Area and the Programming of Funds**

GEF Agency: UNDP; Trust Fund: GET; Country/ Regional/ Global: Ecuador; Focal Area: Biodiversity; Programming of Funds: BD STAR Allocation: BD-1; Grant / Non- Grant: Grant; GEF Project Grant($): 4,516,210.00; Agency Fee($): 429,040.00; Total GEF Financing($): 4,945,250.00
GEF Agency: Total GEF; Trust Fund: Resourc; Country/ Regional/ Global: es ($); GEF Project Grant($): 4,516,210.00; Agency Fee($): 429,040.00; Total GEF Financing($): 4,945,250.00
```

### Passage B3d325

```text
#### **GEF Financing Table**

**Indicative Trust Fund Resources Requested by Agency(ies), Country(ies), Focal Area and the Programming of Funds**

|GEF<br>Agency|Trust<br>Fund|Country/<br>Regional/<br>Global|Focal Area|Programming<br>of Funds|Grant /<br>Non-<br>Grant|GEF Project<br>Grant($)|Agency<br>Fee($)|Total GEF<br>Financing($)|
|---|---|---|---|---|---|---|---|---|
|CAF|GET|Ecuador|Biodiversity|BD STAR<br>Allocation: BD-1|Grant|2,343,673.00|210,930.00|2,554,603.00|
|CAF|GET|Ecuador|Biodiversity|BD STAR<br>Allocation: BD-3|Grant|1,666,419.00|149,978.00|1,816,397.00|
|**Total GEF**|**Resourc**|**es ($)**||||**4,010,092.00**|**360,908.00**|**4,371,000.00**|
```

### Passage B4e7e6

```text
##### **GEF Financing Table**

**Indicative Trust Fund Resources Requested by Agency(ies), Country(ies), Focal Area and the Programming of Funds**

|GEF<br>Agency|Trust<br>Fund|Country/<br>Regional/<br>Global|Focal Area|Programming<br>of Funds|Grant /<br>Non-<br>Grant|GEF Project<br>Grant($)|Agency<br>Fee($)|Total GEF<br>Financing($)|
|---|---|---|---|---|---|---|---|---|
|WWF-<br>US|GET|Cameroon|Biodiversity|BD STAR<br>Allocation: BD-1|Grant|3,519,725.00|316,775.00|3,836,500.00|
|**Total GEF**|**Resourc**|**es ($)**||||**3,519,725.00**|**316,775.00**|**3,836,500.00**|
```

### Passage Bd9fe5

```text
ANNEX A: FINANCING TABLES

#### **GEF Financing Table**

**Indicative Trust Fund Resources Requested by Agency(ies), Country(ies), Focal Area and the Programming of Funds**

GEF Agency: UNEP; Trust Fund: GET; Country/ Regional/ Global: Mozambique; Focal Area: Chemicals and Waste; Programming of Funds: Mercury; Grant / Non- Grant: Grant; GEF Project Grant($): 4,500,000.00; Agency Fee($): 427,500.00; Total GEF Financing($): 4,927,500.00
GEF Agency: Total GEF; Trust Fund: Resourc; Country/ Regional/ Global: es ($); GEF Project Grant($): 4,500,000.00; Agency Fee($): 427,500.00; Total GEF Financing($): 4,927,500.00
```

### Passage B2a49e

```text
### M&E

Component Type Trust Fund
Technical Assistance GET
GEF Project Financing ($) Co-financing ($)
190,943.00 162,375.00

Outcome:

Project implementation and results are systematically monitored, evaluated and reported to support accountability, adaptive management and compliance with GEF requirements

Indicator: # of direct and indirect beneficiaries, disaggregated by gender, age group, ethnicity, and disability status.

Target: At least 6,000 direct beneficiaries, of which at least 40% are women, and 100,000 indirect beneficiarie

Output:

Project monitoring and evaluation system operationalized to track implementation progress, results and beneficiary data across all components

Component Balances: Project Components; GEF Project Financing ($); Co-financing ($)
Component Balances: 1. Realignment of public-sector policies and integrated governance frameworks for effective implementation of the NBSAP and NDCs; 1,767,617.00; 9,419,506.00
Component Balances: 2. Biodiversity-based production, value chains and investment for sustainable landscapes; 1,666,419.00; 19,453,991.00
Component Balances: 3. Knowledge Management and Strategic Communication for Biodiversity Mainstreaming; 194,156.00; 2,524,858.00
Component Balances: M&E; 190,943.00; 162,375.00
Component Balances: Subtotal; 3,819,135.00; 31,560,730.00
Component Balances: Project Management Cost; 190,957.00; 1,652,144.00
Component Balances: Total Project Cost ($); 4,010,092.00; 33,212,874.00
```

### Passage B9d4af

```text
#### **GEF Financing Table**

**Indicative Trust Fund Resources Requested by Agency(ies), Country(ies), Focal Area and the Programming of Funds**

Official Use Only Page 43 of 49





|GEF<br>Agency|Trust<br>Fund|Country/<br>Regional/<br>Global|Focal Area|Programming<br>of Funds|Grant /<br>Non-<br>Grant|GEF Project<br>Grant($)|Agency<br>Fee($)|Total GEF<br>Financing($)|
|---|---|---|---|---|---|---|---|---|
|UNEP|GET|Mozambique|Chemicals<br>and Waste|Mercury|Grant|4,500,000.00|427,500.00|4,927,500.00|
|**Total GEF**|**Resourc**|**es ($)**||||**4,500,000.00**|**427,500.00**|**4,927,500.00**|
```

### Passage B1d205

```text
#### **Indicative Focal Area Elements**

Programming Directions: BD-1-1; Trust Fund: GET; GEF Project Financing($): 2,258,105.00; Co-financing($): 40923760
Programming Directions: BD-1-5; Trust Fund: GET; GEF Project Financing($): 2,258,105.00; Co-financing($): 40923759
Programming Directions: Total Project Cost; GEF Project Financing($): 4,516,210.00; Co-financing($): 81,847,519.00
```

### Passage Bfcaa0

```text
#### **GEF Financing Table**

**Indicative Trust Fund Resources Requested by Agency(ies), Country(ies), Focal Area and the Programming of Funds**

|GEF<br>Agency|Trust<br>Fund|Country/<br>Regional/<br>Global|Focal<br>Area|Programming<br>of Funds|Grant /<br>Non-<br>Grant|GEF Project<br>Grant($)|Agency<br>Fee($)|Total GEF<br>Financing($)|
|---|---|---|---|---|---|---|---|---|
|UNIDO|SCCF-<br>A|Cuba|Climate<br>Change|SCCF-A Country<br>allocation|Grant|2,639,726.00|250,774.00|2,890,500.00|
|**Total GEF**|**Resourc**|**es ($)**||||**2,639,726.00**|**250,774.00**|**2,890,500.00**|
```

### Passage B2faa1

```text
#### **GEF Financing Table**

**Indicative Trust Fund Resources Requested by Agency(ies), Country(ies), Focal Area and the Programming of Funds**

|GEF<br>Agency|Trust<br>Fund|Country/<br>Regional/<br>Global|Focal Area|Programming<br>of Funds|Grant /<br>Non-<br>Grant|GEF Project<br>Grant($)|Agency<br>Fee($)|Total GEF<br>Financing($)|
|---|---|---|---|---|---|---|---|---|
|UNDP|GET|Ecuador|Biodiversity|BD STAR<br>Allocation: BD-1|Grant|4,516,210.00|429,040.00|4,945,250.00|
|**Total GEF**|**Resourc**|**es ($)**||||**4,516,210.00**|**429,040.00**|**4,945,250.00**|
```

## Question: What are the key risks and mitigation measures?

### Passage B38ae6

```text
There is also<br>a risk that strengthened conservation enforcement, including increased<br>patrols and tighter regulation of access to forest resources, could have<br>unintended adverse impacts on livelihoods, food security, and cultural<br>practices if not implemented in a rights-based and carefully managed manner.<br>Mitigation measures: The project will apply FPIC principles; establish<br>transparent and inclusive representation criteria for community structures;<br>ensure participation of women, youth, and marginalized Baka members;<br>support independent facilitation by trusted civil society organizations such as<br>RACOPY and ASBABUK; and support the establishment of a functioning<br>Grievance Redress Mechanism (GRM) and train stakeholders on the GRM,<br>how to manage and access grievances. The project will also deliver human<br>rights training for park personnel; strengthen multi stakeholders’ consultative<br>platforms to foster collaboration and dialogue, reinforce local governance<br>structures to ensure more inclusive decision-making, enhance the<br>participation of IP&LC and women in decision making bodies, and<br>implement signed MoU between ASBABUK and MINFOF granting greater<br>access to IP to natural resources in protected area and surrounding forests.<br>Detailed mitigation measures have been described for environmental risks in<br>Section 4.2 and Table 2 and for social mitigation in Section 4.4 and table 3 of<br>the ESMF.|
|---|---|---|
|Political and<br>Governance|Substantial|Authoritarian Rule and Weak Political Pluralism which limits civic space,<br>restriction on participation can constrain open dialogue and project<br>legitimacy. Risk mitigation measures The project will ensure that project<br>governance structures (steering committee, advisory groups) include all<br>stakeholders (CSOs, communities, women, Indigenous Peoples) Succession<br>risk and political uncertainty with the upcoming election. Risk mitigation<br>measures Build strong partnerships with decentralized/local government and<br>community-based organizations to buffer against national-level disruptions.<br>Corruption, clientelism & nepotism leads to potential misuse of funds,<br>favoritism in procurement, or elite capture of project benefits. Risk mitigation<br>measures Safeguard project funds through use of a Financial administrator<br>who adheres to strict procurement rules aligned with GEF/WWF standards in<br>close cooperation with the government. This will disrupt the corruption cycle<br>and capacitate the government in procurement procedures. Governance risks<br>through weakpublic administrations,centralization,andpoor service|

Official Use Only Page 20 of 31
```

### Passage B35ec7

```text
Risk will be mitigated through clear implementation arrangements, targeted capacity building, technical assistance, coordination mechanisms, territorial engagement, and monitoring systems that support adaptive management.: Stakeholder risks may arise if IPLCs, producer organizations, women, youth, GADs, MSMEs, financial institutions, or other local actors are not sufficiently engaged or do not perceive clear benefits from project interventions. The residual risk is low because the project has been designed around participatory planning, territorial engagement, and multi-stakeholder implementation. Mitigation measures include continued consultations, co-design of SBSAPs and local measures, culturally appropriate engagement, gender-responsive participation, involvement of key stakeholder groups in governance arrangements, and grievance mechanisms.
Other; Moderate; Achievement of outcomes will require coordination across national institutions, GADs, IPLCs, producer organizations, MSMEs, academia, NGOs, and financial institutions. Risk will be mitigated through clear implementation arrangements, targeted capacity building, technical assistance, coordination mechanisms, territorial engagement, and monitoring systems that support adaptive management.: External shocks such as health emergencies, mobility restrictions, natural disasters, security constraints, or abrupt changes in market conditions could affect consultations, field activities, value chains, finance mobilization, and implementation timelines. The project will mitigate these risks by maintaining flexibility in work planning, using local implementation partners and territorial teams where feasible, incorporating adaptive management, allowing remote or hybrid coordination when needed, and designing value chain and finance activities with sufficient contingency for changing market and operating conditions
Overall Risk Rating; Low; Achievement of outcomes will require coordination across national institutions, GADs, IPLCs, producer organizations, MSMEs, academia, NGOs, and financial institutions. Risk will be mitigated through clear implementation arrangements, targeted capacity building, technical assistance, coordination mechanisms, territorial engagement, and monitoring systems that support adaptive management.: The overall residual risk rating is assessed as Low, reflecting the expected level of risk after the application of mitigation measures across all categories. Although some contextual and fiduciary risks are rated Moderate, these are considered manageable due to the project’s alignment with existing national frameworks, established institutional capacities, CAF oversight, GGGI technical support, participatory implementation approach, and mitigation measures embedded in the design. No individual residual risk is expected to significantly compromise the achievement of project outcomes.
```

### Passage Bfc205

```text
||Rating|Explanation of risk and mitigation measures|
|---|---|---|
|CONTEXT|||
|Climate|Moderate|Cuba is highly exposed to hurricanes, floods and droughts that may dis-rupt supply chains,<br>pilot demonstrations and institutional workplans. The project would aim to mitigate these<br>risks by prioritizing resilient technol-ogies, integrating climate-risk screening into design,<br>and aligning with national climate adaptation planning. Residual risk remains substantial<br>due to external climatic conditions.|
|Environmental<br>and Social|Low|The measures are expected to be well received by the public, as they will<br>improve their current access to and use of electricity.|
|Political and<br>Governance|Moderate|Shifts in government priorities, inter-ministerial coordination delays or<br>competing agendas may affect policy reforms. Mitigation includes strong<br>PSC oversight, alignment with national strategies, and continuous dialogue<br>with MINEM, CITMA, MINDUS, UNE and the Institute of Non-State<br>Economic Actors. These measures keep residual governance risk at a<br>moderate level.|
|INNOVATION|||
|Institutional and<br>Policy|Moderate|The project depends on sustained coordination among multiple institu-tions<br>involved in energy, climate adaptation and critical service delivery. Delays in<br>inter-institutional coordination, limited alignment of mandates, or insufficient<br>integration of climate resilience considerations into sectoral plan-ning could<br>reduce implementation effectiveness and the uptake of pro-ject results. To<br>mitigate this risk, the project will establish clear coordina-tion arrangements<br>from the outset, define roles and responsibilities for participating institutions,<br>and support regular technical consultation and validationprocesses. The|

Official Use Only Page 20 of 31
```

### Passage B8a9a8

```text
There is a risk that benefits, representation, and decision-making authority intended for IP&LCs—particularly Baka communities—could be captured by local elites, better-connected intermediaries, or a narrow group of representatives, thereby undermining equitable participation, accountability, and the legitimacy of project- supported governance bodies and benefit-sharing arrangements. There is also a risk that strengthened conservation enforcement, including increased patrols and tighter regulation of access to forest resources, could have unintended adverse impacts on livelihoods, food security, and cultural practices if not implemented in a rights-based and carefully managed manner. Mitigation measures: The project will apply FPIC principles; establish transparent and inclusive representation criteria for community structures; ensure participation of women, youth, and marginalized Baka members; support independent facilitation by trusted civil society organizations such as RACOPY and ASBABUK; and support the establishment of a functioning Grievance Redress Mechanism (GRM) and train stakeholders on the GRM, how to manage and access grievances. The project will also deliver human rights training for park personnel; strengthen multi stakeholders’ consultative platforms to foster collaboration and dialogue, reinforce local governance structures to ensure more inclusive decision-making, enhance the participation of IP&LC and women in decision making bodies, and implement signed MoU between ASBABUK and MINFOF granting greater access to IP to natural resources in protected area and surrounding forests. Detailed mitigation measures have been described for environmental risks in Section 4.2 and Table 2 and for social mitigation in Section 4.4 and table 3 of the ESMF.: Authoritarian Rule and Weak Political Pluralism which limits civic space, restriction on participation can constrain open dialogue and project legitimacy. Risk mitigation measures The project will ensure that project governance structures (steering committee, advisory groups) include all stakeholders (CSOs, communities, women, Indigenous Peoples) Succession risk and political uncertainty with the upcoming election. Risk mitigation measures Build strong partnerships with decentralized/local government and community-based organizations to buffer against national-level disruptions. Corruption, clientelism & nepotism leads to potential misuse of funds, favoritism in procurement, or elite capture of project benefits. Risk mitigation measures Safeguard project funds through use of a Financial administrator who adheres to strict procurement rules aligned with GEF/WWF standards in close cooperation with the government. This will disrupt the corruption cycle and capacitate the government in procurement procedures. Governance risks through weakpublic administrations,centralization,andpoor service
```

### Passage Ba5f11

```text
||Rating|Explanation of risk and mitigation measures|
|---|---|---|
|CONTEXT|||
|Climate|Moderate|There is a risk that increasing climate variability and extreme weather events<br>will impact farming seasons and the regular availability of water, reducing<br>food security, and increasing pressure on forests through shifting agriculture.<br>As temperatures rise, weather patterns become more unpredictable, leading to<br>shifts in traditional farming cycles. This can result in shorter growing<br>seasons, altered planting and harvesting times, and increased vulnerability to<br>extreme weather events such as droughts, floods, and storms. Risk mitigation<br>measure added to project design: IP&LC farmers will be trained in lowimpact agricultural<br>techniques and in weather data collection and analysis to<br>be used in climate predictions to adapt to changing farming periods to reduce<br>deforestation effects from shifting agricultural practices. Climate change<br>considerations have been integrated during project design and will be<br>integrated throughout implementation. This comprehensive approach ensures<br>that the project remains resilient and responsive to environmental changes,<br>safeguarding both the ecosystem and the livelihoods of the communities<br>involved. During sensitization and awareness raising on low impact<br>agriculture, the project will also inform the beneficiary communities that<br>there will be no compensations in case of a worst-case scenario whereby<br>there is complete loss in food production due extreme weather conditions|
|Environmental<br>and Social|Moderate|There is a risk that competing land and resource uses and social exclusion of<br>women and IP&LC are sources of conflicts among stakeholders despite the<br>existing legal framework which could escalate into conflict, undermine trust,<br>and disrupt project activities. Environmental risks have been identified in<br>Section 3.2 of the ESMF. Some of these risks include - potential adverse<br>environmental impacts that may result from activities implemented by the<br>project such as small infrastructure development that could disrupt<br>ecosystems;thepromotion of alternative livelihoods(small scale agriculture|

Official Use Only

6/12/2026

Page 19 of 31
```

### Passage B7c783

```text
The<br>residual risk is low because the project has been designed around participatory<br>planning, territorial engagement, and multi-stakeholder implementation.<br>Mitigation measures include continued consultations, co-design of SBSAPs<br>and local measures, culturally appropriate engagement, gender-responsive<br>participation, involvement of key stakeholder groups in governance<br>arrangements, and grievance mechanisms.|
|Other|Moderate|External shocks such as health emergencies, mobility restrictions, natural<br>disasters, security constraints, or abrupt changes in market conditions could<br>affect consultations, field activities, value chains, finance mobilization, and<br>implementation timelines. The project will mitigate these risks by maintaining<br>flexibility in work planning, using local implementation partners and territorial<br>teams where feasible, incorporating adaptive management, allowing remote or<br>hybrid coordination when needed, and designing value chain and finance<br>activities with sufficient contingency for changing market and operating<br>conditions|
|Overall Risk<br>Rating|Low|The overall residual risk rating is assessed as Low, reflecting the expected<br>level of risk after the application of mitigation measures across all categories.<br>Although some contextual and fiduciary risks are rated Moderate, these are<br>considered manageable due to the project’s alignment with existing national<br>frameworks, established institutional capacities, CAF oversight, GGGI<br>technical support, participatory implementation approach, and mitigation<br>measures embedded in the design. No individual residual risk is expected to<br>significantly compromise the achievement of project outcomes.|
```

### Passage B25dc5

```text
### Key Risks

CONTEXT
Climate; Rating: Moderate; Explanation of risk and mitigation measures: There is a risk that increasing climate variability and extreme weather events will impact farming seasons and the regular availability of water, reducing food security, and increasing pressure on forests through shifting agriculture. As temperatures rise, weather patterns become more unpredictable, leading to shifts in traditional farming cycles. This can result in shorter growing seasons, altered planting and harvesting times, and increased vulnerability to extreme weather events such as droughts, floods, and storms. Risk mitigation measure added to project design: IP&LC farmers will be trained in lowimpact agricultural techniques and in weather data collection and analysis to be used in climate predictions to adapt to changing farming periods to reduce deforestation effects from shifting agricultural practices. Climate change considerations have been integrated during project design and will be integrated throughout implementation. This comprehensive approach ensures that the project remains resilient and responsive to environmental changes, safeguarding both the ecosystem and the livelihoods of the communities involved.
```

### Passage B1c309

```text
|||delivery reduce local buy-in or government support to the project. Risk<br>mitigation measures The project has several components and activities which<br>will strengthen local governance structures, and provide targeted capacity<br>building to local partners. In addition it will use adaptive management to<br>regularly adjust activities to reflect local institutional realities.|
|---|---|---|
|INNOVATION|||
|Institutional and<br>Policy|Substantial|There is a risk that weak institutional environment and weak enforcement of<br>PA laws will allow illegal hunting, bushmeat trade, and resource exploitation<br>to continue, undermining conservation outcomes. Risk mitigation measures<br>The project will strengthen local management bodies to ensure participation<br>of women and Indigenous people in decision making bodies, reactivate and<br>reinforce multi stakeholders’ consultation platforms (component 1), facilitate<br>knowledge and information sharing among stakeholders and ensure greater<br>participation of BBNP in TRIDOM landscape initiatives.
```

### Passage B8199b

```text
The project will not support the physical expansion of mining operations. Social risks also include potential adverse effects on local communities, vulnerable groups and cultural practices in or near ASGM areas, as well as the risk that women and other potentially excluded groups may not benefit equitably from consultations, training, formalization support, finance or technology if project measures are not intentionally inclusive. During the PPG phase, the project will undertake a safeguards assessment, stakeholder consultations and site screening to identify such risks and define appropriate mitigation measures. A stakeholder engagement plan and project-level grievance mechanism will be established, and consultation processes will be designed to ensure meaningful participation of affected communities and other relevant stakeholders. Mitigation measures will include gender-responsive outreach, sex-disaggregated participation monitoring, targeted support to women’s participation and leadership, and accessible grievance pathways. In this context, the project’s formalization, capacity-building and stakeholder engagement activities are expected to reduce rather than increase these risks, provided that safeguard requirements and inclusive design measures are integrated into project preparation and implementation from the outset.
CONTEXT: Political and Governance; Rating: Moderate; Explanation of risk and mitigation measures: Political and governance risks are considered moderate in light of Mozambique’s recent post-electoral instability and ongoing insecurity in Cabo Delgado province. Although the principal ASGM intervention areas currently under consideration, including Manica and Niassa, are not directly affected by active conflict, the broader national context may still affect institutional continuity, field access and implementation conditions. The Implementing Agency will monitor the situation closely in coordination with the Government of Mozambique and the United Nations Country Team (UNCT), and implementation modalities will be adjusted as needed to safeguardproject
```

### Passage B62a50

```text
## Key Risks

CONTEXT
Climate; Rating: Moderate; Explanation of risk and mitigation measures: Cuba is highly exposed to hurricanes, floods and droughts that may dis-rupt supply chains, pilot demonstrations and institutional workplans. The project would aim to mitigate these risks by prioritizing resilient technol-ogies, integrating climate-risk screening into design, and aligning with national climate adaptation planning. Residual risk remains substantial due to external climatic conditions.
Environmental and Social; Rating: Low; Explanation of risk and mitigation measures: The measures are expected to be well received by the public, as they will improve their current access to and use of electricity.
Political and Governance; Rating: Moderate; Explanation of risk and mitigation measures: Shifts in government priorities, inter-ministerial coordination delays or competing agendas may affect policy reforms. Mitigation includes strong PSC oversight, alignment with national strategies, and continuous dialogue with MINEM, CITMA, MINDUS, UNE and the Institute of Non-State Economic Actors. These measures keep residual governance risk at a moderate level.
```

## Question: How does the Cuba project contribute to the country's NDC?

### Passage Bc7ab4

```text
As part of the Global Program on Climate-Resilient Renewable Energy Systems (G-RES), the project also contributes to the broader programme goal of supporting renewable energy systems that are climate-resilient, operationally robust and supportive of sustainable development in highly exposed island and coastal settings. At the national level, the project is closely aligned with Cuba’s climate and sustainable development priorities, including the State Plan for Climate Change (Tarea Vida), which provides the overarching framework for national climate adaptation efforts, particularly in relation to risk reduction, climate resilience-building and the protection of vulnerable territories and essential services.

<mark>While Cuba's National Adaptation Plan (NAP)</mark> is <mark>still under formulation, the country's adaptation effort</mark> is <mark>framed</mark> by <mark>two principal national instruments: the State Plan</mark> to <mark>Confront Climate Change (Tarea Vida) and the updated Nationally Determined Contribution (NDC 3.0).</mark>
```

### Passage Bd412a

```text
#### **Coordination and Cooperation with Ongoing Initiatives and Project.**

Does the GEF Agency expect to play an execution role on this project?

The project aligns closely with Cuba’s national climate priorities, including Tarea Vida and the country’s updated Nationally Determined Contribution (NDC 3.0, February 2025). It will coordinate with and complement ongoing initiatives to ensure coherence, avoid duplication, and maximize synergies, including: • The GEF project in Cuba is part of the G-RES program, which comprises a global-regional component and a growing portfolio of national projects. The global-regional project (GEF ID: 12229) will accelerate national progress by strengthening coordination, ensuring policy coherence, facilitating SIDS–SIDS cooperation, and sharing best practices in climate risk assessments, energy policy development, and integrated resource and climate resilience planning—including gender responsive and socially inclusive approaches

• Accelerating Cuban low-carbon and circular solutions for micro-, small and medium-sized enterprises (GEF ID: 12227) – The project will coordinate, where relevant, with the GEF-8 Cuba project focused on lowcarbon and circular solutions for MSMEs. Although primarily mitigation-oriented, important synergies are

expected in relation to institutional strengthening, capacity building, knowledge generation and the promotion of practical, context-appropriate solutions under Cuban conditions.
```

### Passage Bac419

```text
A broad set of stakeholders will be critical to achieving these outcomes. CUBAENERGIA is expected to play a central role in partial project execution, while relevant national authorities, energy sector institutions, operators of selected critical facilities, and academia will contribute to planning, implementation and uptake. Other relevant public institutions involved in climate adaptation, energy planning and service delivery will be involved to ensure coherence and sustainability. Private sector participation may be relevant in selected areas related to technology supply, technical services and implementation support, as appropriate. These actors will not only contribute to project delivery, but will also be among the main beneficiaries of strengthened capacities, improved planning tools and more resilient service provision.

The project fits within the current landscape of national climate and energy efforts by complementing ongoing investments and policy processes rather than duplicating them. It will build on existing national priorities on climate adaptation, resilience and renewable energy, while helping to bridge the gap between policy ambition and operational practice in the specific area of climate-resilient energy services. It also draws on lessons from previous and ongoing work in Cuba and elsewhere showing the importance of combining institutional strengthening with practical demonstrations and knowledge capture. Its main climate adaptation benefits will include improved resilience of selected critical systems, facilities and communities, enhanced continuity of essential services during climate-related disruptions, stronger institutional capacity to assess and manage climate risks in the energy sector, and better conditions for replication and broader uptake of climate-resilient energy solutions in Cuba.

In this sense, the project is aligned with national priorities for climate resilience and sustainable development, while contributing directly to the objectives of the Global Program on Climate-Resilient Renewable Energy Systems (G-RES). As a national project under the wider G-RES framework, it will address country-specific barriers to climate-resilient renewable energy deployment in Cuba, while drawing on the programme’s global-

Official Use Only Page 10 of 31





regional support architecture, including shared knowledge, methodologies, standards and cross-country learning. In doing so, the project will support the broader G-RES goal of advancing climate-resilient renewable energy systems that enhance energy security, reduce vulnerability to climate-related disruptions and strengthen the sustainability of energy transition efforts in climate-exposed island contexts.

#### B. PROJECT DESCRIPTION
```

### Passage B3cd44

```text
##### Project Title

Global programme on climate-resilient renewable and efficient systems in small island developing States – national project in Cuba

|Region|GEF Project ID|
|---|---|
|Latin America and the Caribbean|12369|
|Country(ies)|Type of Project|
|Cuba|MSP|
|GEF Agency(ies):|GEF Agency ID|
|UNIDO|260258|
|Executing Partner|Executing Partner Type|
|Determined at PPG||
|GEF Focal Area (s)|Submission Date|
|Climate Change|6/8/2026|
|Project Sector (CCM Only)||

###### Climate Change Adaptation Sector
```

### Passage B87aaf

```text
• Program for the Ecological Transition Towards Sustainable Municipalities (AICS–EU–UNDP): Coordination will focus on aligning local-level clean energy and capacity-building activities relevant to MSMEs and pilot demonstrations.

- Participation in Carbon Markets (UNDP – Climate Promise): Coordination will ensure consistency

- with national MRV systems and emerging voluntary carbon market frameworks.

• Technological and Business Upgrade Program for Agrochemical and Agricultural Machinery Industries (Government of Russia – UNIDO): Synergies are expected in industrial modernization, energy efficiency, and technology upgrading.

• Cuba’s Biennial Transparency Reports and National Communications (GEF-funded): Coordination will ensure consistency in greenhouse gas accounting and integration of results into national transparency processes.

Coordination mechanisms and institutional arrangements

As the GEF Agency, UNIDO is expected to support project execution through overall fiduciary oversight, technical supervision, and quality assurance in line with GEF policies and procedures. UNIDO will work with the Government of Cuba and the designated Executing Entity (once confirmed) to support the establishment of implementation arrangements and ensure coordination with relevant national and international initiatives. Project coordination will be ensured through the establishment of a Project Steering Committee (PSC) and a Project Management Unit (PMU). The PSC will provide strategic guidance, ensure alignment with national policies and ongoing initiatives, and endorse annual workplans and budgets. It is expected to include representatives from relevant ministries (including energy and environment), key national institutions, and the GEF Agency.

A PMU will be established within the Executing Entity (once confirmed) and will be responsible for day-today coordination, monitoring and reporting, stakeholder engagement, and implementation of project activities. The PMU will operate under the oversight of the GEF Agency and will serve as the primary interface for coordination with ongoing initiatives, facilitating information sharing, technical exchanges, and, where feasible, the sharing of expertise and resources.

#### **Core Indicators**

#### META INFORMATION – SCCF

SCCF-B (Window B) on: technology transfer; SCCF-A (Window-A) on climate Change: adaptation
SCCF-B (Window B) on: false; SCCF-A (Window-A) on climate Change: true

Is this project LDCF SCCF challenge program?

##### **false**

This Project involves at least one small island developing State(SIDS).

##### **true**

This Project involves at least one fragile and conflict affected state.

##### **false**

This Project will provide direct adaptation benefits to the private sector.

##### **false**

This Project is explicitly related to the formulation and/or implementation of national adaptation plans (NAPs).
```

### Passage Bddcfa

```text
#### **Coordination and Cooperation with Ongoing Initiatives and Project.**

Does the GEF Agency expect to play an execution role on this project?

If so, please describe that role here. Also, please add a short explanation to describe cooperation with ongoing initiatives and projects, including potential for co-location and/or sharing of expertise/staffing

The project aligns closely with Cuba’s national climate priorities, including Tarea Vida and the country’s updated Nationally Determined Contribution (NDC 3.0, February 2025). It will coordinate with and complement ongoing initiatives to ensure coherence, avoid duplication, and maximize synergies, including: • The GEF project in Cuba is part of the G-RES program, which comprises a global-regional component and a growing portfolio of national projects. The global-regional project (GEF ID: 12229) will accelerate national progress by strengthening coordination, ensuring policy coherence, facilitating SIDS–SIDS cooperation, and sharing best practices in climate risk assessments, energy policy development, and integrated resource and climate resilience planning—including gender responsive and socially inclusive approaches
```

### Passage B1823f

```text
While Cuba's National Adaptation Plan (NAP) is still under formulation, the country's adaptation effort is framed by two principal national instruments: the State Plan to Confront Climate Change (Tarea Vida) and the updated Nationally Determined Contribution (NDC 3.0).

Tarea Vida is Cuba's national legislation on climate change — approved by the Council of Ministers on 25 April 2017, it is the instrument of highest legal status on the subject and is implemented and overseen by CITMA. It comprises five strategic actions and 11 tasks directed at reducing climate impacts in vulnerable zones, and explicitly includes the implementation of measures in programmes and projects linked to renewable energy, energy efficiency, health and tourism — the energy and energy-dependent critical-service sectors at the centre of this project. In its current implementation phase, Tarea Vida prioritizes the energy sector and frames renewable energy not only as a mitigation measure but as a means of ensuring service continuity under contingency and climate-related stress conditions, directly consistent with the project's focus on the climate resilience of the electricity system and the critical services that depend on it.

Cuba's updated NDC (NDC 3.0, February 2025) reinforces this framing: it identifies adaptation as the country's highest national priority, anchors adaptation action in Tarea Vida, raises Cuba's renewable energy ambition, and explicitly references the NAP process now underway, fostering coherence between the instruments as the NAP is completed.

The project is therefore aligned with Cuba's operative national adaptation framework. At the same time, explicit treatment of the climate resilience of energy systems and energy-dependent critical services remains limited in current national instruments; the project directly addresses this gap by generating the energy-sector climate-risk assessments, climate resilience-planning tools and priority action roadmaps (Component 1) that feed into national adaptation planning and the emerging NAP.

At the regional and international levels, the project supports implementation of the Paris Agreement through its contribution to adaptation and resilience-building, while also complementing the objectives of the Antigua and Barbuda Agenda for SIDS (ABAS) and the broader SIDS agenda on climate resilience, sustainable energy transitions and strengthened adaptive capacity to climate impacts .

#### D. POLICY REQUIREMENTS

#### **Gender Equality and Women’s Empowerment:**

We confirm that gender dimensions relevant to the project have been addressed as per GEF Policy and are clearly articulated in the Project Description (Section B).

Yes
```

### Passage Bc4ca2

```text
## Indicative Project Overview

### Project Objective

Strengthening the adaptive capacity to climate impacts Cuba’s electricity system and energy-dependent critical services by integrating climate-resilient renewable energy, grid and storage solutions, supported by vulnerability assessments, climate resilience planning and targeted demonstration projects
```

### Passage B8a538

```text
• Accelerating Cuban low-carbon and circular solutions for micro-, small and medium-sized enterprises (GEF ID: 12227) – The project will coordinate, where relevant, with the GEF-8 Cuba project focused on lowcarbon and circular solutions for MSMEs. Although primarily mitigation-oriented, important synergies are

Official Use Only Page 17 of 31





expected in relation to institutional strengthening, capacity building, knowledge generation and the promotion of practical, context-appropriate solutions under Cuban conditions.

• Program for the Ecological Transition Towards Sustainable Municipalities (AICS–EU–UNDP): Coordination will focus on aligning local-level clean energy and capacity-building activities relevant to MSMEs and pilot demonstrations.

- Participation in Carbon Markets (UNDP – Climate Promise): Coordination will ensure consistency

- with national MRV systems and emerging voluntary carbon market frameworks.

• Technological and Business Upgrade Program for Agrochemical and Agricultural Machinery Industries (Government of Russia – UNIDO): Synergies are expected in industrial modernization, energy efficiency, and technology upgrading.

• Cuba’s Biennial Transparency Reports and National Communications (GEF-funded): Coordination will ensure consistency in greenhouse gas accounting and integration of results into national transparency processes.

Coordination mechanisms and institutional arrangements

As the GEF Agency, UNIDO is expected to support project execution through overall fiduciary oversight, technical supervision, and quality assurance in line with GEF policies and procedures. UNIDO will work with the Government of Cuba and the designated Executing Entity (once confirmed) to support the establishment of implementation arrangements and ensure coordination with relevant national and international initiatives. Project coordination will be ensured through the establishment of a Project Steering Committee (PSC) and a Project Management Unit (PMU). The PSC will provide strategic guidance, ensure alignment with national policies and ongoing initiatives, and endorse annual workplans and budgets. It is expected to include representatives from relevant ministries (including energy and environment), key national institutions, and the GEF Agency.

A PMU will be established within the Executing Entity (once confirmed) and will be responsible for day-today coordination, monitoring and reporting, stakeholder engagement, and implementation of project activities. The PMU will operate under the oversight of the GEF Agency and will serve as the primary interface for coordination with ongoing initiatives, facilitating information sharing, technical exchanges, and, where feasible, the sharing of expertise and resources.

#### **Core Indicators**

Explain the methodological approach and underlying logic to justify target levels for Core and Sub-Indicators (max. 250 words, approximately 1/2 page)
```

### Passage Bb470c

```text
A broad set of stakeholders will be critical to achieving these outcomes. CUBAENERGIA is expected to play a central role in partial project execution, while relevant national authorities, energy sector institutions, operators of selected critical facilities, and academia will contribute to planning, implementation and uptake. Other relevant public institutions involved in climate adaptation, energy planning and service delivery will be involved to ensure coherence and sustainability. Private sector participation may be relevant in selected areas related to technology supply, technical services and implementation support, as appropriate. These actors will not only contribute to project delivery, but will also be among the main beneficiaries of strengthened capacities, improved planning tools and more resilient service provision.

The project fits within the current landscape of national climate and energy efforts by complementing ongoing investments and policy processes rather than duplicating them. It will build on existing national priorities on climate adaptation, resilience and renewable energy, while helping to bridge the gap between policy ambition and operational practice in the specific area of climate-resilient energy services. It also draws on lessons from previous and ongoing work in Cuba and elsewhere showing the importance of combining institutional strengthening with practical demonstrations and knowledge capture. Its main climate adaptation benefits will include improved resilience of selected critical systems, facilities and communities, enhanced continuity of essential services during climate-related disruptions, stronger institutional capacity to assess and manage climate risks in the energy sector, and better conditions for replication and broader uptake of climate-resilient energy solutions in Cuba.

In this sense, the project is aligned with national priorities for climate resilience and sustainable development, while contributing directly to the objectives of the Global Program on Climate-Resilient Renewable Energy Systems (G-RES). As a national project under the wider G-RES framework, it will address country-specific barriers to climate-resilient renewable energy deployment in Cuba, while drawing on the programme’s global-

regional support architecture, including shared knowledge, methodologies, standards and cross-country learning. In doing so, the project will support the broader G-RES goal of advancing climate-resilient renewable energy systems that enhance energy security, reduce vulnerability to climate-related disruptions and strengthen the sustainability of energy transition efforts in climate-exposed island contexts.
```

## Question: How many hectares of landscape will be under improved management?

### Passage B9cb1e

```text
##### **Indicator 4 Area of landscapes under improved practices (hectares; excluding protected areas)**

|Ha(Expected at PIF)|Ha(Expected at CEO Endorsement)|Ha(Achieved at MTR)|Ha(Achieved at TE)|
|---|---|---|---|
|60312|0|0|0|

Official Use Only Page 16 of 37





##### **Indicator 4.1 Area of landscapes under improved management to benefit biodiversity (hectares, qualitative assessment, non-certified)**

Ha (Expected at PIF) Ha (Expected at CEO Endorsement) Ha (Achieved at MTR) Ha (Achieved at TE) 60,312.00

##### **Indicator 4.2 Area of landscapes under third-party certification incorporating biodiversity considerations**

Ha (Expected at PIF) Ha (Expected at CEO Endorsement) Ha (Achieved at MTR) Ha (Achieved at TE)

##### **<mark>Type/Name of Third Party Certification</mark>**

**Indicator 4.3 Area of landscapes under sustainable land management in production systems**

Ha (Expected at PIF) Ha (Expected at CEO Endorsement) Ha (Achieved at MTR) Ha (Achieved at TE)
```

### Passage B6b786

```text
● CI 4.1. Area of landscapes under improved management to benefit biodiversity was estimated based on the area that could be supported by the project in communal lands. The average territorial extent of a medium-sized Indigenous community is approximately 5,000 hectares, and management interventions will be implemented in four communities per Jaguar Conservation Unit (UCJ), across four UCJs, so the total area under wildlife management would be around 80,000 hectares. Subtracting the 10% under restoration under CI 3.2 to avoid double counting, the net area is 72,000 hectares.

● CI 4.3. Area of landscapes under sustainable land management in production systems was estimated based on the area that could be supported by the project using a cost per unit of area basis. The cost per unit was estimated based on similar past experiences of these types of interventions. The total number of farms to be supported is estimated at 30 farms or production systems of 50 hectares in each of the four landscapes. Under those assumptions, the total area is 6,000 hectares.

● CI 4.5. Terrestrial OECMs supported indicator was estimated based on the area of selected OECMs supported by the project. The selected OECMs include: Río Anzu Reserve (300 hectares), Yacuma (262 hectares), Ruku Kawsay (1,438 hectares); and Urku Samay (3,737 hectares).

● CI 11. Direct beneficiaries disaggregated by sex was estimated as follows: Work will be carried out in 16 communities, with an average of 60 families, each with a household of five members, typically comprising 52% men and 48% women. In addition, there will be 400 beneficiaries (40% women) from the public sector, including technical staff from MAE, local governments, and other institutions. The estimated total number of direct beneficiaries is therefore 5,600.

Footnote 27: Core Indicator 6 Greenhouse Gas Emissions Mitigated (metric tons of CO2e): TBC.

During PPG Phase, the project will incorporate the quantification of mitigation benefits within the results framework, measuring avoided emissions and carbon stock conservation associated with habitat protection, connectivity conservation, and fragmentation reduction across targeted jaguar landscapes. Recognized ex-ante carbon accounting methodologies will be used to quantify avoided emissions and carbon benefits associated with forest conservation interventions.
```

### Passage B389b4

```text
78. The following is a description of the approaches used for the calculation of each selected GEB:

● CI 1.2 Terrestrial protected areas under improved management effectiveness indicator was estimated by identifying the protected areas that would be supported by the project through Biodiversity Plans and other measures to improve management effectiveness. These include Cotacachi-Cayapas NP (243,638 hectares), Yasuní NP (1,022,700 hectares), Llanaganates NP (219,918 hectares), Sumaco Napo-Galeras NP (205,249 hectares), El Pambilar Wildlife Reserve (3,123 hectares), and Cuyabeno Wildlife Production Reserve (590,112 hectares).

● CI 3.2. Area of forests and forest land under restoration was estimated based on the area that could be supported by the project in communal lands. The average territorial extent of a medium-sized Indigenous community is approximately 5,000 hectares, and management interventions will be implemented in four communities per Jaguar Conservation Unit (JCU), across four JCUs, so the total area under wildlife management would be around 80,000 hectares. We assume that 10% of that area (8,000 hectares) will be under restoration.
```

### Passage B11ee0

```text
50. The project will also support sustainable management and climate-change adaptation practices across at least 30,000 hectares of priority landscapes. These practices may include biodiversity-friendly production systems, restoration-compatible productive practices, soil and water conservation measures, agroecological and silvopastoral approaches, fire-risk reduction, conservation agreements, and other measures identified through SBSAPs and ecosystem risk analyses. By linking these practices to territorial planning, conservation mechanisms, and value chain incentives, the project will generate landscape-level benefits rather than isolated production improvements.

51. Under Outcome 2.2, producer organizations and local actors will be strengthened to support sustainable production, biodiversity conservation, and climate resilience. At least eight producer organizations will receive support in organizational management, sustainable production, biodiversitybased value chains, market access, sustainable finance, and cooperative governance. The project will also train at least 600 institutional and local actors, with at least 40 percent women, to strengthen capacities for biodiversity management, sustainable production, climate adaptation, and territorial planning. These actions will improve the ability of local actors to adopt and maintain practices that contribute to GEBs.
```

### Passage B1805e

```text
#### **Core Indicators**

##### **Indicator 4 Area of landscapes under improved practices (hectares; excluding protected areas)**

Ha(Expected at PIF): 30000; Ha(Expected at CEO Endorsement): 0; Ha(Achieved at MTR): 0; Ha(Achieved at TE): 0

##### **Indicator 4.1 Area of landscapes under improved management to benefit biodiversity (hectares, qualitative assessment, non-certified)**

Ha(Expected at PIF): 30,000.00
```

### Passage Bb53b0

```text
###### _<u>Indicators:</u>_

_CI 4.1: 60,312 hectares of landscapes under improved management to benefit biodiversity_

_CI 5.1: 178,661 hectares of marine habitat under improved practices to benefit biodiversity_

_- 400 technical staff from GADs and other key stakeholders trained on marine and coastal management_

- _-A 70% increase in institutional, technical, and coordination capacity for marine-coastal spatial planning, as measured through a standardized capacity assessment such as the UNDP Capacity Development Scorecard (baseline vs. endline) (at least 40% of total participants are women)_

_- Two (2) CIM technical sub-committees created and demonstrating improved coordination capacity, as evidenced by regular meetings, documented decisions, and implementation of agreed actions (at least 40% of total participants in the CIM technical sub-committees are women)_

- _Twelve (12) marine and coastal plans (3 ICMP and 9 MBASMP) developed and/or updated (at least 40% of total participants in the plan consultations are women)_

###### Output:

- 1.1.1. Comprehensive technical, institutional and participatory assessment of marine-coastal zones conducted

1.1.2 Capacity-building program for local governments (GADs) and key stakeholders implemented

1.1.3 Inter-institutional governance and coordination mechanisms for ICM established

1.1.4 Marine–coastal management plans for prioritized local governments (GADs) developed

### 2. Implementation and financing of prioritized ICM initiatives

|Component Type|Trust Fund|
|---|---|
|Technical Assistance|GET|
|GEF Project Financing ($)|Co-financing ($)|
|2,242,419.00|62,810,324.00|

###### Outcome:

2.1 Improved ICM plans financing and implementation by local governments (GADs), institutional actors, and local stakeholders
```

### Passage B1a67e

```text
#### **Core Indicators**

##### **Indicator 4 Area of landscapes under improved practices (hectares; excluding protected areas)**

Ha(Expected at PIF): 60312; Ha(Expected at CEO Endorsement): 0; Ha(Achieved at MTR): 0; Ha(Achieved at TE): 0

##### **Indicator 4.1 Area of landscapes under improved management to benefit biodiversity (hectares, qualitative assessment, non-certified)**

Ha (Expected at PIF) Ha (Expected at CEO Endorsement) Ha (Achieved at MTR) Ha (Achieved at TE) 60,312.00

##### **Indicator 4.2 Area of landscapes under third-party certification incorporating biodiversity considerations**

Ha (Expected at PIF) Ha (Expected at CEO Endorsement) Ha (Achieved at MTR) Ha (Achieved at TE)

##### **Type/Name of Third Party Certification**

**Indicator 4.3 Area of landscapes under sustainable land management in production systems**

Ha (Expected at PIF) Ha (Expected at CEO Endorsement) Ha (Achieved at MTR) Ha (Achieved at TE)
```

### Passage Bce337

```text
##### **Indicator 4 Area of landscapes under improved practices (hectares; excluding protected areas)**

|Ha(Expected at PIF)|Ha(Expected at CEO Endorsement)|Ha(Achieved at MTR)|Ha(Achieved at TE)|
|---|---|---|---|
|30000|0|0|0|

##### **Indicator 4.1 Area of landscapes under improved management to benefit biodiversity (hectares, qualitative assessment, non-certified)**

|Ha(Expected at PIF)|Ha(Expected at CEO Endorsement)|Ha(Achieved at MTR)|Ha(Achieved at TE)|
|---|---|---|---|
|30,000.00||||
```

### Passage B1fb6d

```text
17. The project will generate Global Environmental Benefits by improving the management of at least 30,000 hectares of landscapes under biodiversity-friendly and climate-resilient practices, reducing pressures on habitats and threatened species, enhancing ecological connectivity, strengthening biodiversity monitoring and territorial planning, and generating an estimated 808,814 tCO2e in climate mitigation co-benefits through improved land-use practices and reduced degradation pressures. It will also directly benefit at least 6,000 people, of whom at least 40 percent will be women, through technical assistance, governance participation, sustainable production, biodiversity-based value chains, and access to finance. These benefits will be achieved by shifting incentives and capacities in the landscapes, rather than through isolated activities.
```

## Question: What renewable energy technologies will be deployed in Cuba?

### Passage B0f549

```text
<mark>systems</mark> for <mark>extreme natural events—supporting decision-making—</mark> is <mark>acknowledged; but they recognized that regarding the vulnerabilities</mark> of <mark>the national electricity system and the increase</mark> in <mark>renewable energy sources more work</mark> is <mark>needed.</mark>

<mark>Discussion with the Ministry</mark> of <mark>Energy and Mines</mark> of <mark>Cuba (MINEM) centred around climate resilience</mark> in <mark>relation</mark> to <mark>the National Energy Transition Strategy (NETS). MINEM colleagues pointed out that climate resilience and climate adaptation are included indirectly</mark> in <mark>the principle</mark> of <mark>environmental sustainability which cut across the NETS. They highlighted that within the ongoing process and national effort</mark> of <mark>shifting the Cuba’s energy matrix towards more renewable energy sources, climate adaptation</mark> is a <mark>critical factor</mark> for <mark>technology maintenance, which</mark> is <mark>the current initial focus</mark> of <mark>MINEM</mark> for <mark>the country.</mark>

<mark>MINEM colleagues see the proposed GEF SCCF-A project highly important and timely</mark> for <mark>Cuba.</mark>

<mark>Unión Eléctrica</mark> de <mark>Cuba (UNE) and</mark> its <mark>provincial Electric Companies</mark> in <mark>Santiago</mark> de <mark>Cuba province and Holguin province.</mark>
```

### Passage Bb9099

```text
It is <mark>imperative</mark> for <mark>Cuba</mark> to <mark>fully factor-in climate resilience</mark> in <mark>the repowering</mark> of <mark>the Gibara</mark> I <mark>Wind Farm and development and construction</mark> of <mark>future wind and solar</mark> PV <mark>parks. Measures such</mark> as <mark>the use</mark> of <mark>medium-power (e.g. smaller) wind turbines capable</mark> of <mark>withstanding stronger wind loads; the introduction</mark> of <mark>underground power lines</mark> in <mark>grid critical locality; reinforcement and other climate resilience solutions</mark> for <mark>solar</mark> PV <mark>parks; are examples</mark> of <mark>interventions that would allow</mark> to <mark>reduce the economic and social damage caused</mark> to <mark>the country</mark> by <mark>these phenomenon.</mark> In <mark>addition</mark> to <mark>that,</mark> it is <mark>imperative</mark> for <mark>Cuba</mark> to <mark>also fully integrate climate resilience</mark> in <mark>the medium- and long-term strategies and plans</mark> for <mark>the modernization</mark> of its <mark>power grid,</mark> to <mark>maximise value creation</mark> for <mark>the country and minimize costs and losses. The potential</mark> to <mark>reduce climate vulnerabilities and increase adaptive capacity</mark> to <mark>climate change impacts through modern transmission and distribution networks monitoring and communication systems and energy planning will</mark> be <mark>analyzed</mark> by <mark>the project.</mark>
```

### Passage B6e5c8

```text
Hurricanes’ passage always causes damages also to other energy system/grid assets such as substations, distribution lines and pole transformers due to flooding, strong wind and flying debris, water incursion and

contamination. Cuba’s power substations are particularly critical, yet highly fragile, nodes of the island's energy/power system. Crippled by aging Soviet-era infrastructure and underinvestment, these substations struggle to manage the distribution of electricity from thermal plants, a handful of independent producers (like Energas), and newly integrated solar PV parks. In an effort to avoid total dependence on its failing thermoelectric power stations and imported oil, Cuba has rapidly expanded its renewable energy infrastructure, adding roughly 800 MW of new solar park capacity. However, the integration of these localized solar facilities into the aging, centralized power substations and system continues to pose severe technical hurdles due to the lack of adequate power management infrastructure capacities and concequent inevitable grid instability.
```

### Passage B859b7

```text
## Indicative Project Overview

### Project Objective

Strengthening the adaptive capacity to climate impacts Cuba’s electricity system and energy-dependent critical services by integrating climate-resilient renewable energy, grid and storage solutions, supported by vulnerability assessments, climate resilience planning and targeted demonstration projects
```

### Passage B51db6

```text
<mark>contamination. Cuba’s power substations are particularly critical, yet highly fragile, nodes</mark> of <mark>the island's energy/power system. Crippled</mark> by <mark>aging Soviet-era infrastructure and underinvestment, these substations struggle</mark> to <mark>manage the distribution</mark> of <mark>electricity from thermal plants,</mark> a <mark>handful</mark> of <mark>independent producers (like Energas), and newly integrated solar</mark> PV <mark>parks.</mark> In an <mark>effort</mark> to <mark>avoid total dependence</mark> on its <mark>failing thermoelectric power stations and imported oil, Cuba has rapidly expanded</mark> its <mark>renewable energy infrastructure, adding roughly 800 MW</mark> of <mark>new solar park capacity. However, the integration</mark> of <mark>these localized solar facilities into the aging, centralized power substations and system continues</mark> to <mark>pose severe technical hurdles due</mark> to <mark>the lack</mark> of <mark>adequate power management infrastructure capacities and concequent inevitable grid instability.</mark>
```

### Passage B75477

```text
##### Project Summary

The project aims to strengthen the adaptive capacity of Cuba’s electricity system and energy-dependent critical services by integrating climate-resilient renewable energy, grid and storage solutions, supported by climate vulnerability assessments, resilience planning and targeted demonstration projects. It will do so through an integrated approach combining: (i) climate risk assessments, resilience planning tools and priority action roadmaps for selected energy systems and critical services; (ii) strengthened technical capacities, institutional mechanisms and knowledge products to support the planning, operation and broader uptake of climate-resilient energy solutions; and (iii) demonstration projects in selected critical facilities and communities to generate practical evidence on approaches that can maintain service continuity during and after climate-related disruptions.

The project is expected to generate adaptation benefits through improved resilience of selected facilities and communities, enhanced continuity of essential services during extreme weather events, stronger institutional capacity to assess and manage climate risks in the energy sector, and improved conditions for the replication and broader uptake of climate-resilient energy solutions in Cuba.
```

### Passage B2f9ef

```text
Official Use Only Page 24 of 31





|**Name of stakeholder**|**Person**<br>**met/consulted**|**Main topic(s) discussed**|**Key issues raised/ highlighted**|
|---|---|---|---|
|province (belonging<br>to UNE)|||considerations, plans and<br>technologies would be very<br>convenient to then scale-up the<br>model to other wind parks and so<br>reducing the climate change<br>impacts on the population.|
|Ministry of Energy<br>and Mines of Cuba<br>(MINEM)|Rosell Guerra<br>Campaña, Director,<br>Renewable Energy<br>Department<br>Elaine Moreno<br>Carnet. Director,<br>Human Resources<br>for Directives<br>Jorge Luis Isaac<br>Pino. Specialist of<br>renewable energy<br>Department|v. Climate- resilience<br>in the National<br>Energy Transition<br>Strategy.|- Climate resilience included<br>indirectly in the principle of<br>environmental sustainability.<br>- In the process of shifting the<br>energy matrix towards renewable<br>energy sources, the climate<br>adaptation is a critical factor for<br>technology maintenance; current<br>initial focus of MINEM for the<br>country.<br>- MINEM considers the project<br>highly important and timely for<br>Cuba|
|Ministry of Science,<br>Technology and<br>Environment of Cuba<br>(CITMA)|Rudy Montero<br>Mata, Deputy<br>Minister of<br>Environment<br>Odalys Goicochea<br>Cardoso, General<br>Director of<br>Environment<br>Jesús Guerra Bell,<br>Specialist of the<br>Internation<br>Cooperation<br>Department (GEF<br>Focal Point)|vi. Climate- resilience<br>in the National<br>Strategy, Nationally<br>Determined<br>Contribution of Cuba,<br>State Plan to address<br>climate change in<br>Cuba “Tarea Vida”|- The three documents are<br>interconnected, recognizing the<br>critical importance of adapting to<br>the climate change impacts, as<br>well as the guidelines and actions<br>to minimize them.<br>- Special Emphasis on<br>strengthening monitoring,<br>surveillance, and early warning<br>systems, raising risk awareness,<br>and increasing the level of<br>knowledge and degree of<br>participation of the population.<br>- The country's progress in early<br>warning and notification systems<br>for extreme natural events—<br>supporting decision-making—is<br>acknowledged; however, is<br>limited the scope regarding the<br>vulnerabilities of the national<br>electricity system and the<br>increase in renewable energy<br>sources.|

(Please upload to the portal documents tab any stakeholder engagement plan or assessments that have been done during the PIF development phase.)

Official Use Only Page 25 of 31





#### **Private Sector**

Will there be private sector engagement in the project?

#### Yes

And if so, has its role been described and justified in the section B project description?

#### Yes
```

### Passage Bdf246

```text
Cuba has already established an important policy and institutional foundation for climate adaptation and resilience-building, including through the State Plan for Climate Change, Tarea Vida, and national efforts to strengthen the role of renewable energy in the electricity mix. At the same time, significant gaps remain in the systematic assessment of climate risks affecting energy systems and energy-dependent critical services, in the application of climate resilience planning tools tailored to these systems, and in the operational experience needed to deploy and manage climate-resilient energy solutions under Cuban conditions. Existing efforts provide an important baseline, but without additional support, climate-related hazards will continue to increase pressure on electricity systems and on the continuity of critical services, while practical opportunities to build climate resilience through targeted renewable energy, storage and grid solutions will remain insufficiently tested, documented and replicated.
```

### Passage B3cacf

```text
It is imperative for Cuba to fully factor-in climate resilience in the repowering of the Gibara I Wind Farm and development and construction of future wind and solar PV parks. Measures such as the use of medium-power (e.g. smaller) wind turbines capable of withstanding stronger wind loads; the introduction of underground power lines in grid critical locality; reinforcement and other climate resilience solutions for solar PV parks; are examples of interventions that would allow to reduce the economic and social damage caused to the country by these phenomenon. In addition to that, it is imperative for Cuba to also fully integrate climate resilience in the medium- and long-term strategies and plans for the modernization of its power grid, to maximise value creation for the country and minimize costs and losses. The potential to reduce climate vulnerabilities and increase adaptive capacity to climate change impacts through modern transmission and distribution networks monitoring and communication systems and energy planning will be analyzed by the project.
```

## Question: How will gender equality be mainstreamed in the project?

### Passage Ba0cb8

```text
##### Taxonomy

Climate Change Adaptation, Climate Change, Focal Areas, Adaptation Tech Transfer, National Adaptation Plan, Small Island Developing States, Mainstreaming adaptation, Climate resilience, Climate information, Gender Mainstreaming, Gender Equality, Gender results areas, Capacity, Knowledge and Research, Capacity Development, Knowledge Generation, Training, Workshop, Knowledge Exchange, South-South, Field Visit, Sex-disaggregated indicators, Knowledge Generation and Exchange, Strengthen institutional capacity and decision-making, Influencing models, Transform policy and regulatory environments, Education, Communications, Stakeholders, Awareness Raising, Academia, Civil Society

|Type of Trust Fund|Project Duration (Months)|
|---|---|
|SCCF|60|
|GEF Project Grant: (a)|GEF Project Non-Grant: (b)|
|2,639,726.00|0.00|
|Agency Fee(s) Grant: (c)|Agency Fee(s) Non-Grant (d)|
|250,774.00|0.00|
|Total GEF Financing: (a+b+c+d)|Total Co-financing|
|2,890,500.00|18,478,082.00|
|PPG Amount: (e)|PPG Agency Fee(s): (f)|
|100,000.00|9,500.00|

Official Use Only Page 3 of 31





|PPG total amount: (e+f)|Total GEF Resources: (a+b+c+d+e+f)|
|---|---|
|109,500.00|3,000,000.00|
|Project Tags||
|CBIT: No NGI: No SGP: No Innovation: NoCompetitive|Window: No|
```

### Passage Bc5eff

```text
Private Sector: Yes

56. Preliminary analysis indicates that women and men may experience different levels of participation, access to resources and influence over decision-making processes related to marine and coastal management, sustainable livelihoods and territorial planning. Women may face barriers associated with unequal participation in local governance structures, limited representation in environmental decision-making processes and unequal access to economic opportunities linked to marine and coastal resources.

57. To address these differences, the project will apply gender-responsive approaches throughout implementation, including promoting equitable participation in consultation and decision-making processes, strengthening opportunities for women’s leadership and participation within governance mechanisms, and supporting equal access to project benefits, training opportunities and sustainable livelihood initiatives where relevant.
```

### Passage B910eb

```text
58. Gender-responsive measures and indicators will be incorporated into project implementation and monitoring frameworks, including sex-disaggregated indicators where applicable, to monitor participation and benefits generated through project interventions. Additional gender analysis and stakeholder consultations conducted during implementation will further refine gender-responsive actions and ensure adaptive implementation where needed. The project budget will incorporate human and financial resources to monitor the effectiveness of gender mainstreaming actions.

Provide a brief summary and list of names and dates of consultations.
```

### Passage Be5545

```text
#### **Gender Equality and Women’s Empowerment:**

We confirm that gender dimensions relevant to the project have been addressed as per GEF Policy and are clearly articulated in the Project Description (Section B).

Yes
```

### Passage B87523

```text
###### 3.2 Mainstreamed gender and social and environmental strategies

###### _Indicators:_

_- Eight (8) tools (e.g., protocols, plans) for safeguards and gender mainstreaming implemented_

_- 100% of diagnostic assessments, planning instruments (ICMP/MBASMP), and field actions that fully meet SES quality criteria (screening completed; mitigation measures integrated; SESA applied if required; site-specific environmental assessments and ESMPs prepared when needed; consultations properly documented)._

###### Output:

3.1.1 Knowledge management and communication strategy developed and implemented, incorporating a gender-responsive and culturally relevant approach

3.1.2 Harmonized information management system and spatial data platform for ICM established

### M&E

Component Type: Technical Assistance; Trust Fund: GET
Component Type: GEF Project Financing ($); Trust Fund: Co-financing ($)
Component Type: 215,052.00; Trust Fund: 1,086,588.00

###### Outcome:

###### 3.3 Strengthened M&E to support adaptive management

###### _Indicators:_

- _Annual Project Implementation Reports (PIRs), one (1) Mid-Term Review (MTR) and one (1) Terminal Evaluation (TE) report_

###### Output:

3.3.1 Project Monitoring and Evaluation (M&E) Plan implemented
```

### Passage B60359

```text
##### Taxonomy

Influencing models, Strengthen institutional capacity and decision-making, Convene multi-stakeholder alliances, Deploy innovative financial instruments, Stakeholders, Beneficiaries, Local Communities, Civil Society, Community Based Organization, Non-Governmental Organization, Academia, Communications, Awareness Raising, Capacity, Knowledge and Research, Enabling Activities, Capacity Development, Knowledge Generation, Gender Equality, Gender Mainstreaming, Women groups, Sexdisaggregated indicators, Gender-sensitive indicators, Gender results areas, Access and control over natural resources, Participation and leadership, Access to benefits and services, Knowledge Generation and Exchange, Focal Areas, Biodiversity, Protected Areas and Landscapes, Coastal and Marine Protected Areas, Productive Seascapes, Mainstreaming, Tourism, Fisheries, Climate Change, Climate Change Adaptation, Ecosystem-based Adaptation, Mainstreaming adaptation, Indigenous Peoples

|Type of Trust Fund|Project Duration (Months)|
|---|---|
|GET|54|
|GEF Project Grant: (a)|GEF Project Non-Grant: (b)|
|4,516,210.00|0.00|
|Agency Fee(s) Grant: (c)|Agency Fee(s) Non-Grant (d)|
|429,040.00|0.00|
|Total GEF Financing: (a+b+c+d)|Total Co-financing|
|4,945,250.00|81,847,519.00|
|PPG Amount: (e)|PPG Agency Fee(s): (f)|
|50,000.00|4,750.00|

Official Use Only

6/15/2026

Page 3 of 37



|PPG total amount: (e+f)|Total GEF Resources: (a+b+c+d+e+f)|
|---|---|
|54,750.00|5,000,000.00|

Project Tags CBIT: No NGI: No SGP: No Innovation: No Competitive Window: No
```

### Passage B9b2ae

```text
#### Gender Dimensions

The project will take into account relevant gender dimensions in line with UNIDO’s guidelines and will ensure that gender considerations are reflected in project design and implementation. The project will therefore seek to promote inclusive participation in relevant consultations, training and project activities, and will incorporate gender-responsive considerations in the further development of assessments, implementation arrangements and monitoring approaches during project preparation.

A more detailed gender analysis and corresponding gender-responsive actions will be developed during the PPG phase and reflected in the full project document and results framework, including, as appropriate, the use of sex-disaggregated data and gender-sensitive indicators. Knowledge Management (KM)

Official Use Only Page 16 of 31





The project will generate technical, operational and institutional knowledge through climate vulnerability assessments, climate resilience planning processes, capacity-building activities and practical demonstration projects. This knowledge will be documented, managed and shared through technical guidance materials, operational tools, lessons learned and other knowledge products that support both national uptake and contribution to the wider G-RES programme.

The project will also promote learning and broader uptake by translating technical experience into practical guidance for future action. In particular, the documentation of demonstration results, operational lessons and replication potential will help strengthen the evidence base for climate-resilient renewable energy, storage and grid solutions in Cuba.
```

### Passage B902bf

```text
53. **Outcome 3.2: Mainstreamed gender and social and environmental strategies.** Under this Outcome, the project will ensure that gender mainstreaming strategies and social and environmental safeguards are systematically integrated across all components during implementation. Safeguards actions will follow the GAP, the SESP-derived management plans, FPIC requirements in Indigenous territories, and inclusive engagement processes supported by a strong grievance and safeguards management system. These processes will apply a gender- and intersectionality-responsive lens to risk screening, management planning and community engagement, ensuring that differentiated risks, barriers and needs of women, youth, Indigenous Peoples and other groups are identified and addressed across all project landscapes.
```

### Passage B10009

```text
58. Gender-responsive measures and indicators will be incorporated into project implementation and monitoring frameworks, including sex-disaggregated indicators where applicable, to monitor participation and benefits generated through project interventions. Additional gender analysis and stakeholder consultations conducted during implementation will further refine gender-responsive actions and ensure adaptive implementation where needed. The project budget will incorporate human and financial resources to monitor the effectiveness of gender mainstreaming actions.
```

### Passage B8d9d3

```text
#### Gender Dimensions

The project will take into account relevant gender dimensions in line with UNIDO’s guidelines and will ensure that gender considerations are reflected in project design and implementation. The project will therefore seek to promote inclusive participation in relevant consultations, training and project activities, and will incorporate gender-responsive considerations in the further development of assessments, implementation arrangements and monitoring approaches during project preparation.

A more detailed gender analysis and corresponding gender-responsive actions will be developed during the PPG phase and reflected in the full project document and results framework, including, as appropriate, the use of sex-disaggregated data and gender-sensitive indicators. Knowledge Management (KM)

The project will generate technical, operational and institutional knowledge through climate vulnerability assessments, climate resilience planning processes, capacity-building activities and practical demonstration projects. This knowledge will be documented, managed and shared through technical guidance materials, operational tools, lessons learned and other knowledge products that support both national uptake and contribution to the wider G-RES programme.

The project will also promote learning and broader uptake by translating technical experience into practical guidance for future action. In particular, the documentation of demonstration results, operational lessons and replication potential will help strengthen the evidence base for climate-resilient renewable energy, storage and grid solutions in Cuba.
```
