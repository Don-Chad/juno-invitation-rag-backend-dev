"""
Q&A Generation using Groq LLM.

Generates question-answer pairs from documents for the Q&A RAG system.
"""
import json
import time
import re
import tiktoken
from typing import List, Dict, Tuple, Optional
from groq import Groq
from . import config
from .state import state


# Initialize tokenizer
tokenizer = tiktoken.get_encoding("cl100k_base")


def detect_language(text: str) -> str:
    """
    Detect document language (Dutch vs English).
    Simple heuristic based on common Dutch words.
    """
    text_sample = text[:3000].lower()  # Check first 3000 chars
    
    # Common Dutch words/patterns
    dutch_indicators = [
        'van de', 'het', 'een', 'worden', 'zijn', 'deze', 'voor',
        'ook', 'maar', 'naar', 'bij', 'worden', 'niet', 'wordt',
        'energie', 'heeft', 'kunnen', 'nieuwe', 'jaar'
    ]
    
    # Common English words
    english_indicators = [
        'the', 'and', 'that', 'with', 'for', 'are', 'from',
        'this', 'was', 'which', 'their', 'have', 'been'
    ]
    
    dutch_count = sum(1 for word in dutch_indicators if f' {word} ' in text_sample)
    english_count = sum(1 for word in english_indicators if f' {word} ' in text_sample)
    
    # If significantly more Dutch indicators, it's Dutch
    if dutch_count > english_count * 1.5:
        return 'Dutch'
    elif english_count > dutch_count * 1.5:
        return 'English'
    else:
        # Default to Dutch for this village cooperative
        return 'Dutch'


def count_tokens(text: str) -> int:
    """Count tokens in text."""
    return len(tokenizer.encode(text))


def get_qa_count_for_size(token_count: int) -> int:
    """Determine how many Q&As to generate based on document size."""
    if token_count < 5000:
        return config.QA_COUNT_SMALL
    elif token_count < 15000:
        return config.QA_COUNT_MEDIUM
    else:
        return config.QA_COUNT_LARGE


def create_qa_prompt(document_text: str, document_title: str, document_year: Optional[str], 
                     token_count: int, language: str) -> str:
    """Create prompt for Q&A generation with automatic language detection."""
    
    qa_count = get_qa_count_for_size(token_count)
    
    # Extract year from title if not provided
    if not document_year:
        year_match = re.search(r'\b(20\d{2})\b', document_title)
        document_year = year_match.group(1) if year_match else "unknown year"
    
    # Language-specific instructions
    if language == 'Dutch':
        language_instruction = """
TAAL: NEDERLANDS
- Genereer vragen in het NEDERLANDS (Gebaseerd op [document] ([jaar]), [vraag]?)
- Genereer antwoorden in het NEDERLANDS
- Gebruik correcte Nederlandse terminologie en grammatica
- Voorbeeld vraag formaat: "Gebaseerd op {document_title} ({document_year}), wat was de totale productie van hernieuwbare energie?"
"""
        example_q = f"Gebaseerd op {document_title} ({document_year}), wat was de totale productie van hernieuwbare energie?"
        example_a = "De totale productie van hernieuwbare energie bedroeg 450 MWh, wat overeenkomt met 35% van het dorpsverbruik."
        example_context = "In 2023 produceerde de dorpscoöperatie in totaal 450 MWh aan hernieuwbare energie via zonnepanelen en windturbines. Dit komt overeen met ongeveer 35% van het totale energieverbruik van het dorp. Het resterende verbruik wordt gedekt door inkoop van groene stroom."
    else:
        language_instruction = """
LANGUAGE: ENGLISH
- Generate questions in ENGLISH (Based on [document] ([year]), [question]?)
- Generate answers in ENGLISH
- Use proper English terminology and grammar
"""
        example_q = f"Based on {document_title} ({document_year}), what was the total renewable energy production?"
        example_a = "Total renewable energy production was 450 MWh, representing 35% of village consumption."
        example_context = "In 2023, the village cooperative produced a total of 450 MWh of renewable energy through solar panels and wind turbines. This represents approximately 35% of the village's total energy consumption. The remaining consumption is covered by purchasing green electricity."
    
    prompt = f"""You are a precision question-answer generator for a Dutch village energy cooperative knowledge base.

DOCUMENT INFORMATION:
Title: {document_title}
Year: {document_year}
Tokens: {token_count:,}
Language: {language}

⚠️ CRITICAL - TEXT-TO-SPEECH COMPATIBILITY:
Use ONLY these characters in your output:
- Latin letters (A-Z, a-z) with diacritics (à, é, ü, etc.)
- Numbers (0-9)
- ASCII punctuation: . , : ; ! ? ' " ( ) [ ] - / & %
- Essential symbols: € (Euro sign), • (bullet point)
- Smart quotes are OK: ' ' " "

FORBIDDEN characters that will crash the system:
- Chinese/Japanese/Korean characters (CJK): 一起, 中文, etc.
- Emoji: 😊 🎉 ❤️ etc.
- Special Unicode: ≈ § ° ± ☺ ❏ etc.
- En/em dashes: Replace – or — with regular hyphen -
- Ligatures: Replace ﬁ ﬂ ﬀ with fi fl ff
- Ellipsis: Replace … with ...

TAAK: Genereer {qa_count} hoogwaardige vraag-antwoord paren die ALLE belangrijke informatie uit dit document vastleggen.

DOELGROEP: Potentiële deelnemers/leden van de dorpscoöperatie die willen begrijpen:
- Waarom zij moeten deelnemen
- Wat zij moeten doen
- Welke voordelen/verplichtingen zij hebben
- Hoe processen werken
- Welke kosten/vereisten er zijn

KRITIEKE VEREISTEN:
{language_instruction}
1. VRAGEN:
   - Altijd document context opnemen in het NEDERLANDS
   - Wees specifiek en feitelijk
   - Dek ALLE belangrijke informatie: data, cijfers, beleid, beslissingen, namen, locaties
   - Vragen kunnen 10-50 woorden zijn (streef naar duidelijkheid, niet beknoptheid)
   - Neem PRAKTISCHE vragen op die potentiële leden zouden stellen:
     * "Waarom zou ik..."
     * "Wat moet ik..."
     * "Hoe kan ik..."
     * "Wat zijn de vereisten voor..."
     * "Wat zijn de voordelen van..."
   
2. ANTWOORDEN:
   - Direct, feitelijk, GEEN OPVULZINNEN
   - NOOIT zinnen gebruiken zoals "Volgens het rapport" / "Het document stelt"
   - Direct naar de feiten
   - Kan 10-100 woorden zijn afhankelijk van complexiteit
   - Neem specifieke cijfers, data, percentages op indien beschikbaar
   
   ⚠️ KRITIEK - GEEN HALLUCINATIE OF AANNAMES:
   - ALLEEN vermelden wat EXPLICIET in het document staat
   - NIET afleiden, aannemen, of informatie afleiden
   - NIET beweren dat iets "verplicht" is tenzij het document dit expliciet stelt
   - NIET gevolgen vermelden tenzij expliciet genoemd in het document
   - Als een formulier om informatie vraagt, zeg "vraagt om" niet "vereist"
   - Als onzeker of het document het antwoord niet expliciet geeft, genereer dit Q&A paar NIET
   - Voorbeeld FOUT: "Een handtekening is verplicht; zonder wordt het formulier niet geaccepteerd" (aannames over gevolgen)
   - Voorbeeld GOED: "Het formulier vraagt om een handtekening in het veld 'Handtekening'" (vermeldt wat er staat)

3. CONTEXT:
   - Voor elk antwoord: extraheer het relevante tekstfragment uit het document
   - Context moet het antwoord ondersteunen en extra details geven
   - Maximum 500 tokens per context fragment
   - Neem letterlijke citaten op waar mogelijk
   - Help de AI-avatar om het antwoord natuurlijk uit te spreken met voldoende achtergrond
   
4. DEKKING:
   - Important facts deserve multiple questions from DIFFERENT angles
   - Cover introduction, main findings, conclusions, recommendations
   - Don't skip tables, charts, or numerical data
   - Include practical/action-oriented questions for potential members
   - If {qa_count} questions aren't enough to cover all important info, you MAY generate more
   
   ⚠️ VERMIJD REDUNDANTIE:
   - Genereer GEEN vragen die in essentie hetzelfde vragen maar anders geformuleerd
   - Voorbeeld FOUT: "Hoeveel kernreactoren worden gebouwd?" en "Wat is het aantal nieuwe kernreactoren?"
   - Voorbeeld GOED: "Hoeveel kernreactoren worden gebouwd?" en "Wanneer worden de kernreactoren operationeel?"
   - Verschillende aspecten van hetzelfde onderwerp = GOED (aantal vs timing vs locatie vs kosten)
   - Dezelfde vraag herformuleerd = SLECHT (vermijd!)
   - Wees specifiek en gedetailleerd, maar herhaal niet dezelfde informatie

5. ONDERWERP CONTEXT:
   - Dit gaat over een Nederlandse dorpscoöperatie voor energie (Dorpscoöperatie)
   - Onderwerpen: hernieuwbare energie, zonne-/windenergie, gemeenschapsparticipatie, regelgeving, financiën, lidmaatschap
   - Behoud technische termen in originele taal
   - Denk vanuit het perspectief van iemand die overweegt lid te worden

DOCUMENT TEKST:
{document_text}

OUTPUT FORMAAT (alleen JSON):
{{
  "questions_answers": [
    {{
      "question": "{example_q}",
      "answer": "{example_a}",
      "context": "{example_context}",
      "page_hint": 5
    }}
  ]
}}

Genereer {qa_count}+ vraag-antwoord paren in het NEDERLANDS. Output ALLEEN geldige JSON.
"""
    
    return prompt


def validate_qa_pair(qa: Dict, max_question_tokens: int = config.QUESTION_MAX_TOKENS) -> Tuple[bool, Optional[str]]:
    """Validate a single Q&A pair with context."""
    
    # Check required fields
    if 'question' not in qa or 'answer' not in qa:
        return False, "Missing question or answer field"
    
    question = qa['question'].strip()
    answer = qa['answer'].strip()
    context = qa.get('context', '').strip()  # Context is optional but recommended
    
    if not question or not answer:
        return False, "Empty question or answer"
    
    # Warn if context is missing but don't fail
    if not context:
        # Context is helpful but not strictly required
        pass
    
    # Check question token count
    question_tokens = count_tokens(question)
    if question_tokens > max_question_tokens:
        return False, f"Question too long: {question_tokens} tokens (max {max_question_tokens})"
    
    # Check for filler phrases in answer (English and Dutch)
    filler_phrases = [
        # English
        'according to the report',
        'the document states',
        'as mentioned in the document',
        'the report indicates',
        'as stated in the document',
        'the document mentions',
        # Dutch
        'volgens het rapport',
        'volgens het document',
        'het document stelt',
        'het rapport vermeldt',
        'zoals vermeld in het document',
        'zoals vermeld in het rapport',
        'het document geeft aan',
        'volgens de tekst'
    ]
    
    answer_lower = answer.lower()
    for phrase in filler_phrases:
        if phrase in answer_lower:
            return False, f"Answer contains filler phrase: '{phrase}'"
    
    # Check for assumption/inference words that suggest hallucination
    # These patterns often indicate the model is making assumptions
    assumption_patterns = [
        # English - consequence assumptions
        'will not be accepted',
        'will be rejected',
        'is mandatory',
        'must have',
        'it is required',
        'without it',
        'otherwise',
        # Dutch - consequence assumptions  
        'wordt niet geaccepteerd',
        'wordt geweigerd',
        'is verplicht',
        'moet hebben',
        'anders',
        'zonder dit'
    ]
    
    # Only flag if it's making claims about requirements/consequences
    # Allow these words in factual contexts (e.g., "the target is mandatory according to law")
    for pattern in assumption_patterns:
        if pattern in answer_lower:
            # Check if it's preceded by factual indicators
            context_ok = any(indicator in answer_lower for indicator in [
                'states that', 'specifies that', 'defines', 'explicitly',
                'stelt dat', 'specificeert dat', 'definieert', 'expliciet'
            ])
            if not context_ok:
                return False, f"Answer may contain assumption/inference: '{pattern}' (without explicit source)"
    
    return True, None


async def generate_qa_pairs(document_text: str, document_title: str, document_year: Optional[str] = None,
                           dev_mode: bool = False, force_language: Optional[str] = None) -> Tuple[List[Dict], Dict]:
    """
    Generate Q&A pairs from document text using Groq.
    Automatically detects document language or uses forced language override.
    
    Args:
        document_text: Full document text
        document_title: Document title
        document_year: Optional year from document
        dev_mode: Enable verbose output
        force_language: Override language detection (e.g., "Dutch", "English")
    
    Returns:
        (qa_pairs, generation_stats)
    """
    
    start_time = time.time()
    
    # Detect or override language
    if force_language:
        language = force_language
    else:
        language = detect_language(document_text)
    
    # Count tokens in document
    token_count = count_tokens(document_text)
    
    print(f"\n{'='*60}")
    print(f"Q&A GENERATION: {document_title}")
    print(f"{'='*60}")
    print(f"Document language: {language}")
    print(f"Document tokens: {token_count:,}")
    print(f"Target Q&As: {get_qa_count_for_size(token_count)}")
    print(f"{'='*60}\n")
    
    # Create prompt
    prompt = create_qa_prompt(document_text, document_title, document_year, token_count, language)
    prompt_tokens = count_tokens(prompt)
    
    if dev_mode:
        print(f"📝 Prompt tokens: {prompt_tokens:,}")
        print(f"🔄 Sending request to Groq ({config.GROQ_MODEL})...\n")
    
    # Initialize Groq client
    client = Groq(api_key=config.GROQ_API_KEY)
    
    try:
        # Make API call
        response = client.chat.completions.create(
            model=config.GROQ_MODEL,
            messages=[
                {"role": "system", "content": "Je bent een precisie vraag-antwoord generator voor een Nederlandse dorpscoöperatie. Answer in JSON mode. Genereer alleen geldige JSON in het Nederlands."},
                {"role": "user", "content": prompt}
            ],
            temperature=config.GROQ_TEMPERATURE,
            max_completion_tokens=16000,  # Groq requires max_completion_tokens, not max_tokens
            response_format={"type": "json_object"},
            stream=False
        )
        
        # Extract response
        response_text = response.choices[0].message.content
        response_tokens = count_tokens(response_text)
        
        # Parse JSON
        try:
            qa_data = json.loads(response_text)
            qa_pairs = qa_data.get('questions_answers', [])
        except json.JSONDecodeError as e:
            print(f"✗ JSON parsing error: {e}")
            if dev_mode:
                print(f"\nRaw response:\n{response_text[:500]}...\n")
            return [], {
                'success': False,
                'error': f"JSON parsing failed: {e}",
                'tokens_sent': prompt_tokens,
                'tokens_received': response_tokens
            }
        
        # Validate Q&A pairs
        valid_pairs = []
        invalid_count = 0
        
        for idx, qa in enumerate(qa_pairs, 1):
            is_valid, error = validate_qa_pair(qa)
            
            if is_valid:
                valid_pairs.append(qa)
            else:
                invalid_count += 1
                if dev_mode:
                    print(f"⚠️  Q&A {idx} invalid: {error}")
                    print(f"   Q: {qa.get('question', 'N/A')[:100]}...")
        
        # Calculate statistics
        processing_time = int((time.time() - start_time) * 1000)
        
        stats = {
            'success': True,
            'tokens_sent': prompt_tokens,
            'tokens_received': response_tokens,
            'qa_count': len(valid_pairs),
            'invalid_count': invalid_count,
            'processing_time_ms': processing_time,
            'model': config.GROQ_MODEL,
            'language': language
        }
        
        # Update global stats
        state.stats.add_request(prompt_tokens, response_tokens, len(valid_pairs))
        state.stats.processing_time_ms += processing_time
        
        # Print summary
        print(f"\n{'='*60}")
        print(f"✓ Generated {len(valid_pairs)} valid Q&A pairs")
        if invalid_count > 0:
            print(f"⚠️  {invalid_count} invalid pairs (filtered out)")
        print(f"📊 Tokens sent: {prompt_tokens:,}")
        print(f"📊 Tokens received: {response_tokens:,}")
        print(f"⏱️  Time: {processing_time:,} ms")
        print(f"{'='*60}\n")
        
        return valid_pairs, stats
        
    except Exception as e:
        error_msg = f"Groq API error: {e}"
        print(f"✗ {error_msg}")
        state.stats.add_error(error_msg)
        
        return [], {
            'success': False,
            'error': error_msg,
            'tokens_sent': prompt_tokens,
            'tokens_received': 0
        }


def save_qa_pairs_to_file(qa_pairs: List[Dict], document_title: str, output_path: str):
    """Save Q&A pairs to JSON file for inspection."""
    
    output_data = {
        'document_title': document_title,
        'qa_count': len(qa_pairs),
        'generated_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        'qa_pairs': qa_pairs
    }
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    
    print(f"💾 Saved Q&A pairs to: {output_path}")

