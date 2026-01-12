"""
RAG Context Builder Functions
Builds context text from Q&A pairs and document chunks
"""

def build_qa_context(qa_pairs, document_server_enabled=False, document_server_base_url=""):
    """Build context text from Q&A pairs"""
    context_text = """VRAAG-ANTWOORD INFORMATIE:
De volgende vragen en antwoorden komen uit je kennisbank en zijn betrouwbaar en actueel.
Gebruik deze informatie ALTIJD als deze relevant is voor de vraag van de gebruiker.

"""
    
    for idx, qa in enumerate(qa_pairs, 1):
        similarity = qa.get('similarity', 0)
        context_text += f"[Q&A {idx}] (relevantie: {similarity:.2f})\n"
        context_text += f"Bron: {qa.get('source', 'Onbekend')}"
        if qa.get('page'):
            context_text += f" (pagina {qa['page']})"
        context_text += "\n"
        
        # Document server DISABLED - caused blocking imports during RAG queries
        # if document_server_enabled:
        #     try:
        #         from document_server import generate_document_url
        #         doc_url = generate_document_url(qa.get('source', ''), document_server_base_url)
        #         context_text += f"Download: {doc_url}\n"
        #     except ImportError:
        #         pass
        
        context_text += f"Vraag: {qa['question']}\n"
        context_text += f"Antwoord: {qa['answer']}\n"
        
        if 'context' in qa and qa['context'] != qa['answer']:
            context_text += f"Context: {qa['context']}\n"
        
        context_text += "\n"
    
    if document_server_enabled:
        context_text += "[Instructie]: Verwijs naar deze bronnen met [Bron: documentnaam] wanneer je de informatie gebruikt. Wanneer je een bron noemt, geef dan ALTIJD de downloadlink.\n"
    else:
        context_text += "[Instructie]: Verwijs naar deze bronnen met [Bron: documentnaam] wanneer je de informatie gebruikt.\n"
    
    return context_text


def build_chunk_context(docs, document_server_enabled=False, document_server_base_url=""):
    """Build context text from chunk documents"""
    context_text = """DOCUMENTINFORMATIE:
De volgende informatie komt uit de boeken en artikelen van Juno Burger. Dit mag je ook gebruiken voor het antwoord.

"""
    
    for idx, doc in enumerate(docs, 1):
        context_text += f"[Document {idx}]\n"
        context_text += f"Bron: {doc.get('source', 'Onbekend')}\n"
        
        # Document server DISABLED - caused blocking imports during RAG queries
        # if document_server_enabled:
        #     try:
        #         from document_server import generate_document_url
        #         doc_url = generate_document_url(doc.get('source', ''), document_server_base_url)
        #         context_text += f"Download: {doc_url}\n"
        #     except ImportError:
        #         pass
        
        if "summary" in doc:
            context_text += f"Samenvatting: {doc['summary']}\n"
        
        context_text += "Relevante fragmenten:\n"
        
        snippet_count = 0
        for i in range(1, 4):
            snippet_key = f"snippet_{i}"
            if snippet_key in doc:
                snippet_count += 1
                context_text += f"  • Fragment {snippet_count}: {doc[snippet_key]}\n"
        
        context_text += "\n"
    
    if document_server_enabled:
        context_text += "\n"
    else:
        context_text += "\n"
    
    return context_text


def build_combined_qa_context(qa_pairs):
    """Build simplified Q&A context for combined mode"""
    qa_context = """VRAAG-ANTWOORD INFORMATIE:
De volgende vragen en antwoorden komen uit je kennisbank:

"""
    
    for idx, qa in enumerate(qa_pairs, 1):
        qa_context += f"[Q&A {idx}]\n"
        qa_context += f"Bron: {qa.get('source', 'Onbekend')}"
        if qa.get('page'):
            qa_context += f" (p.{qa['page']})"
        qa_context += "\n"
        qa_context += f"Vraag: {qa['question']}\n"
        qa_context += f"Antwoord: {qa['answer']}\n\n"
    
    return qa_context


def build_combined_chunk_context_with_budget(docs, current_context, budget_tokens, estimate_tokens_func, logger):
    """Build chunk context respecting token budget"""
    chunk_context = """\n\nDOCUMENTINFORMATIE:
De volgende documentfragmenten geven extra context:

"""
    
    for idx, doc in enumerate(docs, 1):
        doc_text = f"[Doc {idx}] {doc.get('source', 'Onbekend')}\n"
        
        for i in range(1, 4):
            if f"snippet_{i}" in doc:
                snippet_text = f"  • {doc[f'snippet_{i}']}\n"
                test_context = current_context + chunk_context + doc_text + snippet_text
                
                if estimate_tokens_func(test_context) > budget_tokens:
                    logger.info(f"⚠️  Hit token budget at Doc {idx}, stopping")
                    break
                
                doc_text += snippet_text
        
        chunk_context += doc_text + "\n"
        
        if estimate_tokens_func(current_context + chunk_context) > budget_tokens:
            break
    
    return chunk_context

