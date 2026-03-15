# System Design

## Product Requirements

- Book pages have a QR code
- QR code links to a domain name we control
- Backend application runs an AI agent which can validate answers to questions in the book
- Results will not be saved beyond the current session
- AI agent can provide hints
- AI agent is guided to provide short responses
- When a correct individual answer is provided, AI agent is guided to validate and provide the position of the team/player in the list (e.g., "Correct! That's the Nth team on the list.")   
- The QR code communicates the book id, version, and page number to the backend application
- The backend application uses spreadsheets as a database for book content and links
- The backend application loads the link and uses the AI agent to answer questions about the content

### Example

Book Question: "List the top 20 all-time NFL touchdown leaders."
Answer site: https://www.espn.com/nfl/history/leaders/_/stat/touchdown
QR Code: https://barbooks.ai/book/nfl/leaders/touchdown
User Question: "Is Tom Brady on this list?"
AI Response: "No, Tom Brady is not on this list."
User Question: "Randy Moss?"
AI Response: "Yes, Randy Moss is 4th on the list with 157 TD's"

## Technical Implementation

- Run an LLM locally on my mac
- Expose an API for external calls
- Provide basic limitations on input, such as character limit
- Enforce response length limit
- Provide a basic chat bot like UI
