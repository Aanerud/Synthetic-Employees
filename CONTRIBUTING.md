# Contributing to Shadow Employees

The most impactful contribution you can make is **enriching the personas**. Each shadow employee has a personality, quirks, expertise, and relationships that determine how they behave in Microsoft 365. Richer personas produce more realistic signals.

---

## Adding a New Persona

### 1. Create the folder

```bash
cp -r agents/_template agents/firstname.lastname
```

### 2. Edit `persona.json`

The identity fields must match a real M365 account in the test tenant. The personality fields are where you make them human.

```json
{
  "identity": {
    "name": "Michael Scott",
    "email": "michael.scott@<tenant>.onmicrosoft.com",
    "role": "Regional Manager",
    "department": "Management",
    "job_title": "Regional Manager",
    "office_location": "Scranton Office"
  },
  "personality": {
    "writing_style": "Enthusiastic, uses too many exclamation marks",
    "communication_style": "Warm but awkward, movie quotes",
    "mbti": "ESFP",
    "quirks": [
      "Calls meetings for things that could be an email",
      "Signs off with misattributed quotes"
    ]
  },
  "work_preferences": {
    "email_check_frequency_minutes": 10,
    "response_time_sla_hours": 0.5,
    "timezone": "America/New_York"
  }
}
```

### 3. Write `background.md`

This is the persona's story. Include:
- **MBTI type** and how it shows up at work
- **Personal history** (where they came from, career path)
- **Work quirks** (habits, routines, pet peeves)
- **Communication patterns** (email style, Teams behavior, meeting habits)
- **Signal generation notes** (what kind of M365 traffic they create)

### 4. Write `expertise.md`

What does this person know? What do they research? How do they approach work?

### 5. Write `relationships.md`

Who do they work with? Who do they avoid? How do they communicate with different people?

---

## Enriching an Existing Persona

The `agents/` folder has 95 personas. Most have bare-bones profiles. Pick any employee and add personality.

```bash
# See who needs enrichment
ls agents/*/background.md 2>/dev/null | wc -l   # How many have backgrounds?
ls agents/*/persona.json | wc -l                  # Total personas
```

Edit any of these files:
- `agents/<name>/background.md` - Add MBTI, history, quirks
- `agents/<name>/expertise.md` - Add domain knowledge
- `agents/<name>/relationships.md` - Add team connections

The system reads these files and injects them into the AI prompt. Richer files produce more realistic behavior.

---

## Persona Design Tips

### What Makes a Good Signal Generator

The goal is realistic M365 traffic. A good persona produces:
- **Emails** that read like a real person wrote them
- **Teams messages** at natural frequencies
- **Calendar events** with appropriate attendees
- **File shares** when collaborating

### MBTI as a Behavior Framework

MBTI types map to communication styles:

| Type | Email Style | Teams Style | Meeting Style |
|------|------------|-------------|---------------|
| ESTJ | Direct, bullet points | Brief, action-oriented | Runs tight agendas |
| ENFP | Enthusiastic, long | Emoji-heavy, starts group chats | Goes on tangents |
| INTJ | Formal, precise | Minimal, prefers async | Only when necessary |
| ISFJ | Warm, thorough | Supportive, reacts to everything | Takes notes for everyone |

### Cultural Communication Patterns

Employees are across 14 European countries. Cultural patterns matter:

| Country | Email Formality | Response Speed | Meeting Culture |
|---------|----------------|----------------|-----------------|
| Germany | Formal, structured | Prompt, within SLA | Punctual, agenda-driven |
| Italy | Warm, personal openings | Relaxed timing | Expressive, may run over |
| Sweden | Egalitarian, first names | Steady, consensus-seeking | Fika breaks built in |
| France | Polished, proper salutations | Afternoon responses common | Discussion-oriented |

### Quirks That Generate Signals

The best quirks create M365 activity:
- "Sends motivational quotes every Monday" → weekly email signal
- "Creates a Teams poll for every team lunch" → Teams activity
- "Schedules 1:1s with every new team member" → calendar signals
- "Shares interesting articles in the team channel" → Teams + link signals
- "Always replies-all with a thank you" → email chain signals

### Pop Culture Personas

Steal from fiction. These characters have well-defined behaviors:

**The Office**: Michael Scott (ESFP, high-volume emailer), Dwight Schrute (ESTJ, sends formal memos), Jim Halpert (ENTP, minimal email, lots of Teams chat)

**Futurama**: Professor Farnsworth (INTP, sends rambling technical emails), Hermes Conrad (ISTJ, spreadsheets and compliance emails), Bender (sends nothing, skips meetings)

**Parks & Rec**: Leslie Knope (ENFJ, sends 50 emails before 9am), Ron Swanson (ISTP, one-word replies, declines all meetings)

---

## Adding Personas from the CSV

If you need to create M365 accounts for new personas, update `textcraft-europe.csv` with their data and run:

```bash
python -m src.main import-csv --file textcraft-europe.csv --output agents
```

This creates the persona folder structure. Then enrich the files manually.

---

## Testing Your Persona

```bash
# Verify persona loads correctly
python -c "
from src.agents.persona_loader import PersonaRegistry, to_agency_input_vars
reg = PersonaRegistry()
reg.load_all()
p = reg.get_by_email('your.persona@...')
print(p.name, p.role)
vars = to_agency_input_vars(p)
print(f'{len(vars)} input variables generated')
print(f'Background: {vars[\"Background\"][:100]}...')
"

# Run the full test suite
python tests/test_agency_v2.py
```

---

## Project Structure for Contributors

```
agents/
  _template/              ← Copy this to create a new persona
    persona.json          ← Identity, personality, work preferences
    background.md         ← MBTI, history, quirks
    expertise.md          ← Domain knowledge
    relationships.md      ← Team connections
  katarina.hofer/         ← Example: real persona
  victoria.palmer/        ← Example: real persona
  ...95 total

.github/agents/           ← Agent templates (how the AI thinks)
  employee-kam.md         ← Key Account Manager behavior
  employee-editor.md      ← Editor behavior
  employee-writer.md      ← Writer behavior
  ...8 role templates
```

**Persona files** define WHO the shadow is. **Agent templates** define HOW that role behaves. You contribute personas. The system handles the rest.
