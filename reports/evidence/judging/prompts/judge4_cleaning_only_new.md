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

### Passage C0001

```text
General Project Information

###### Project Title

Innovative and Inclusive Approach to Sustainable Management of Biodiversity and Indigenous Peoples and Local Communities (IP&LCs) Resilient Livelihood in Boumba Bek National Parc of the TRIDOM landscape

Region: Africa; GEF Project ID: 12362
Region: Country(ies); GEF Project ID: Type of Project
Region: Cameroon; GEF Project ID: MSP
Region: GEF Agency(ies):; GEF Project ID: GEF Agency ID
Region: WWF-US; GEF Project ID: G0061
Region: Executing Partner; GEF Project ID: Executing Partner Type
Region: MINFOF; GEF Project ID: Government
Region: MINEPDED; GEF Project ID: Government
Region: GEF Focal Area (s); GEF Project ID: Submission Date
Region: Biodiversity; GEF Project ID: 5/28/2026
Region: Project Sector (CCM Only)

Taxonomy

Focal Areas, Biodiversity, Protected Areas and Landscapes, Community Based Natural Resource Mngt, Terrestrial Protected Areas, Mainstreaming, Agriculture and agrobiodiversity, Biomes, Tropical Rain Forests, Species, Threatened Species

Type of Trust Fund: GET; Project Duration (Months): 60
Type of Trust Fund: GEF Project Grant: (a); Project Duration (Months): GEF Project Non-Grant: (b)
Type of Trust Fund: 3,519,725.00; Project Duration (Months): 0.00
Type of Trust Fund: Agency Fee(s) Grant: (c); Project Duration (Months): Agency Fee(s) Non-Grant (d)
Type of Trust Fund: 316,775.00; Project Duration (Months): 0.00
Type of Trust Fund: Total GEF Financing: (a+b+c+d); Project Duration (Months): Total Co-financing
Type of Trust Fund: 3,836,500.00; Project Duration (Months): 29,922,367.00
Type of Trust Fund: PPG Amount: (e); Project Duration (Months): PPG Agency Fee(s): (f)
Type of Trust Fund: 150,000.00; Project Duration (Months): 13,500.00
Type of Trust Fund: PPG total amount: (e+f); Project Duration (Months): Total GEF Resources: (a+b+c+d+e+f)
Type of Trust Fund: 163,500.00; Project Duration (Months): 4,000,000.00

Project Tags

CBIT: No NGI: No SGP: No Innovation: No Competitive Window: No
```

## Question: What marine protected areas are covered in Ecuador?

### Passage C0002

```text
Map 1. National system of protected areas; protective forest and vegetation and key biodiversity areas in Tropical Dry Forest - Southeastern Ridges.

24. The Tropical Dry Forest landscape, located in Manabí and Santa Elena, represents one of the most threatened and fragmented dry forest systems in Ecuador and the wider Tumbesian region. It hosts specialized and endemic species adapted to seasonal water stress and includes ecological subtypes that provide critical ecosystem services for rural livelihoods, water regulation, soil stability, and climate resilience. However, this landscape is under severe pressure from deforestation, agricultural and livestock expansion, forest fires, land degradation, and unsustainable land-use practices. Climate change compounds these pressures through prolonged droughts, heatwaves, erratic rainfall, and increased fire risk, reducing ecosystem functionality and agricultural productivity. Despite these threats, the landscape offers significant opportunities for ecological restoration, sustainable land management, biodiversity-based businesses, and community-based conservation, particularly where producer organizations, local governments, and community structures are already active.
```

## Question: How will gender equality be mainstreamed in the project?

### Passage C0003

```text
##### Taxonomy

Influencing models, Strengthen institutional capacity and decision-making, Convene multi-stakeholder alliances, Deploy innovative financial instruments, Stakeholders, Beneficiaries, Local Communities, Civil Society, Community Based Organization, Non-Governmental Organization, Academia, Communications, Awareness Raising, Capacity, Knowledge and Research, Enabling Activities, Capacity Development, Knowledge Generation, Gender Equality, Gender Mainstreaming, Women groups, Sexdisaggregated indicators, Gender-sensitive indicators, Gender results areas, Access and control over natural resources, Participation and leadership, Access to benefits and services, Knowledge Generation and Exchange, Focal Areas, Biodiversity, Protected Areas and Landscapes, Coastal and Marine Protected Areas, Productive Seascapes, Mainstreaming, Tourism, Fisheries, Climate Change, Climate Change Adaptation, Ecosystem-based Adaptation, Mainstreaming adaptation, Indigenous Peoples

Type of Trust Fund: GET; Project Duration (Months): 54
Type of Trust Fund: GEF Project Grant: (a); Project Duration (Months): GEF Project Non-Grant: (b)
Type of Trust Fund: 4,516,210.00; Project Duration (Months): 0.00
Type of Trust Fund: Agency Fee(s) Grant: (c); Project Duration (Months): Agency Fee(s) Non-Grant (d)
Type of Trust Fund: 429,040.00; Project Duration (Months): 0.00
Type of Trust Fund: Total GEF Financing: (a+b+c+d); Project Duration (Months): Total Co-financing
Type of Trust Fund: 4,945,250.00; Project Duration (Months): 81,847,519.00
Type of Trust Fund: PPG Amount: (e); Project Duration (Months): PPG Agency Fee(s): (f)
Type of Trust Fund: 50,000.00; Project Duration (Months): 4,750.00

PPG total amount: (e+f): 54,750.00; Total GEF Resources: (a+b+c+d+e+f): 5,000,000.00

Project Tags CBIT: No NGI: No SGP: No Innovation: No Competitive Window: No
```

## Question: How many hectares of landscape will be under improved management?

### Passage C0004

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
