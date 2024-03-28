from fitz import Document

def get_words_from_PDF(doc: Document, start_page: int = 3) -> list[str]:
    '''
    Gets the words from a PDF document from a specified page number until the end of the document.
    Args:
        doc (fitz.Document):
            The PDF document to get words from.
        start_page (int):
            The page number of the PDF document to being getting words from.
            Words from the page will be included in the returned list of words.
            Useful for omitting the table of contents from the list of words to search through for section content later on. 
    Returns:
        all_words (list[str]):
            The list of words from the PDF, beginning at start_page until the end of the document.        
    '''
    all_words = []
    for i in range(start_page, doc.page_count):
        page = doc[i]
        words = page.get_text("words")
        for word in words:
            all_words.append(word[4])
    return all_words


def get_section(start_str: str, end_string: str, words: list[str]) -> str | None:
    '''
    Gets a section of content from a PDF file.
    Returns the text between start_str and end_str.
    Args:
        start_str(str):
            The beginning of the section to return. (i.e., the section's title)
            Will not be included in the returned text.
        end_str(str):
            The beginning of the section after the one being returned. (i.e., the next section's title)
        words(List[str]):
            The list of words to search through.
            From a PDF document.
    Returns:
        section_body(str): The text between start_string and end_str if they are both found.
        None: If start_str or end_str cannot be found.
    TODO: Add support for returning section at end of document.
    '''
    start_words = start_str.split(" ")
    end_words = end_string.split(" ")

    search_start_str = ""
    search_end_str = ""
    start_str_found = False
    end_str_found = False
    section_body = ""
    idx = 0

    for word in words:
        if not start_str_found:
            if word == start_words[idx]:
                # Append to str with a space if not the first word in str
                search_start_str += word if len(search_start_str) == 0 else f" {word}"
                idx += 1
                if search_start_str == start_str:
                    start_str_found = True
                    idx = 0
            else:
                # If text != start_word[idx], reset str and idx
                search_start_str = ""; idx = 0
                
        else:
            # once start_str has been found, append to start_body until end_string is found
            if not end_str_found:
                section_body += word if len(section_body) == 0 else f" {word}"
                if word == end_words[idx]:
                    search_end_str += word if len(search_end_str) == 0 else f" {word}"
                    idx += 1
                    if search_end_str == end_string:
                        # found end_str
                        section_body = section_body[:-len(end_string)-1]    # retroactively remove the begining of the next section (and trailing space) from the end of the section body after the end string is found.
                        return section_body
                else:
                    search_end_str = ""; idx = 0
    
    if not start_str_found:
        print(f'Could not find start_str: "{start_str}"')
    elif not end_str_found:
        print(f'Could not find end_string: "{end_string}"')
    return None


def get_item_after(lst: list[str], item: str) -> str | None:
    '''
    Get the item that comes after a specified item in a list.
    Args:
        lst(List[str]): The list from which to search for the specified item and return the subsequent item.
        item: The target item to search for in the list and return the item that comes after.
    Returns: The elemnt in lst that comes after item.
    '''
    try:
        idx = lst.index(item)
        return lst[idx + 1]
    except ValueError:
        print(f"ValueError - '{item}' not found in list")
        return None
    except IndexError:
        print(f"IndexError - No next item. '{item}' is the last item in the list.")
        return None

