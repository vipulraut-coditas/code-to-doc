# Software Requirements Specification (SRS)
## Library App

> Reverse-engineered from source code by **codedoc** on 2026-10-25. Files analysed: 7. LLM: Claude Code (haiku / sonnet).
>
> This is a *draft* produced by an AI acting as a Business Analyst. Items marked **Low** confidence and everything under *Assumptions* / *Open Questions* must be validated with stakeholders.

## Table of Contents
1. Introduction
2. Overall Description
3. Features and Functional Requirements
4. Non-Functional Requirements
5. Business Rules
6. Data Requirements
7. External Interfaces
8. Assumptions
9. Open Questions for Stakeholders
10. Glossary
Appendix A. Module Overview

## 1. Introduction

### 1.1 Purpose
Provide the backend for a small community library, supporting management of the book catalogue and the lending and return of books to members.

### 1.2 Scope
In scope: book catalogue search and addition, borrowing and returning books, loan rules (due date, loan limit, availability), late fines, librarian-only access control, and intended return receipt emails. Out of scope or not evidenced: member registration, user interface, payments for fines, reporting, reservations, and real authentication. Several endpoints are currently stubs, so the intended behaviour is only partly implemented.

### 1.3 Confidence Legend
- **High** - behaviour is directly visible in the code.
- **Medium** - strongly implied by the code structure or naming.
- **Low** - an educated guess; please confirm.

## 2. Overall Description

### 2.1 Product Overview
A web API (FastAPI) with two feature areas exposed at /books and /loans. Books can be searched by anyone and added by librarians. Members borrow books under lending rules: active members only, a maximum of 3 active loans, a copy must be available, and a 14-day loan period. Late returns incur a fine of 10 INR per day. A return receipt email to the member is intended. Data records exist for books, members and loans.

### 2.2 User Classes and Actors
| Actor | Description |
|---|---|
| Public caller | Anyone who can search the catalogue without a role. |
| Librarian | Staff member who may add books; identified by a 'librarian' role header. |
| Member | Library patron who borrows and returns books. Can be active or inactive. |
| Client application | Software that calls the HTTP API on behalf of users. |
| Email service (SMTP) | External system intended to deliver return receipts to members. |

### 2.3 Technology Stack (observed)
- Python
- FastAPI
- SQLAlchemy
- Pydantic

## 3. Features and Functional Requirements

### 3.1 Catalogue search
Search books by title, author or ISBN using an optional free-text query.

| ID | Requirement | Priority | Confidence | Source |
|---|---|---|---|---|
| FR-001 | The system shall allow any caller to search the book catalogue without requiring a role. | Must | High | app/api/books.py |
| FR-002 | The system shall allow searching books by title, author or ISBN using an optional free-text query. | Must | Medium | app/api/books.py |

### 3.2 Catalogue management
Librarians add books with ISBN, title, author and number of copies.

| ID | Requirement | Priority | Confidence | Source |
|---|---|---|---|---|
| FR-003 | The system shall allow a librarian to add a book to the catalogue with ISBN, title, author and number of copies. | Must | Medium | app/api/books.py, app/models/entities.py |

### 3.3 Borrowing
Members borrow books subject to eligibility, loan limit and availability rules.

| ID | Requirement | Priority | Confidence | Source |
|---|---|---|---|---|
| FR-005 | The system shall allow a member to borrow a book. | Must | Medium | app/api/loans.py, app/services/loan_service.py |
| FR-006 | The system shall refuse a borrow request from an inactive member. | Must | High | app/services/loan_service.py |
| FR-007 | The system shall refuse a borrow request when the member already has 3 active loans, with the message 'Loan limit reached'. | Must | High | app/services/loan_service.py |
| FR-008 | The system shall refuse a borrow request when no copy of the book is available. | Must | High | app/services/loan_service.py |
| FR-009 | The system shall reduce the available copies of a book by one when it is borrowed. | Must | High | app/services/loan_service.py |
| FR-010 | The system shall set the due date to 14 days after the borrow date. | Must | High | app/services/loan_service.py |
| FR-016 | The system shall record each loan with the book, member, borrow date, due date and return date. | Must | Medium | app/models/entities.py |

### 3.4 Returns and fines
Returning a loan restores stock and calculates late fines.

| ID | Requirement | Priority | Confidence | Source |
|---|---|---|---|---|
| FR-011 | The system shall allow a borrowed loan to be returned. | Must | Medium | app/api/loans.py, app/services/loan_service.py |
| FR-012 | The system shall increase the available copies of a book by one when a loan is returned. | Must | High | app/services/loan_service.py |
| FR-013 | The system shall charge a fine of 10 INR per day for each day a book is returned after its due date, and no fine for on-time or early returns. | Must | High | app/services/loan_service.py |
| FR-014 | The system shall use the current date as the return date unless a specific date is supplied. | Should | High | app/services/loan_service.py |

### 3.5 Return receipts
Email receipt sent to the member on return (intended).

| ID | Requirement | Priority | Confidence | Source |
|---|---|---|---|---|
| FR-015 | The system shall send a return receipt email to the member when a loan is returned. | Should | Low | app/api/loans.py |

### 3.6 Role-based access control
Restricts librarian-only actions based on a role header.

| ID | Requirement | Priority | Confidence | Source |
|---|---|---|---|---|
| FR-004 | The system shall refuse requests to add books unless the role header equals 'librarian', responding with HTTP 403 'Librarians only'. | Must | High | app/api/auth.py, app/api/books.py |

## 4. Non-Functional Requirements
| ID | Category | Requirement | Confidence | Source |
|---|---|---|---|---|
| NFR-001 | Security | The system shall restrict librarian-only operations to callers declaring the librarian role. | High | app/api/auth.py |
| NFR-002 | Security | The system should verify caller identity with credentials or tokens rather than a client-supplied role label, which can be forged. | Low | app/api/auth.py |
| NFR-003 | Reliability | The system should keep available-copy counts consistent and prevent a loan from being returned twice. | Low | app/services/loan_service.py |
| NFR-004 | Maintainability | Lending rules should be separate from the API layer and use configurable constants for loan limit, loan period and fine rate. | Medium | app/services/loan_service.py, app/main.py |

## 5. Business Rules
- **BR-001:** Only requests with role 'librarian' may add books.
- **BR-002:** Catalogue search is open to all callers.
- **BR-003:** A book needs ISBN, title, author and number of copies.
- **BR-004:** Inactive members cannot borrow.
- **BR-005:** A member may have at most 3 active loans.
- **BR-006:** A book can be borrowed only if a copy is available.
- **BR-007:** The loan period is 14 days.
- **BR-008:** The fine is 10 INR per day late.
- **BR-009:** Members have role 'member' or 'librarian'.
- **BR-010:** A loan without a return date is still open.

## 6. Data Requirements
| Entity | Description | Key Attributes |
|---|---|---|
| Book | A title in the library catalogue. | id, isbn, title, author, copies_total, copies_available |
| Member | A library patron or staff user. | id, name, email, is_active, role |
| Loan | A borrow of a book by a member. | id, book_id, member_id, borrowed_on, due_on, returned_on |
| Fine | Late-return charge in INR, calculated on return. | amount, days_late |

## 7. External Interfaces
| Interface | Type | Description |
|---|---|---|
| Library HTTP API | REST API | Endpoints under /books and /loans. |
| Return receipt email | Email | SMTP email to members on return (intended only). |
| Database | Database | Persistence via SQLAlchemy presumed from tech stack; not visible in code analysed. |

## 8. Assumptions
- The role header is a placeholder for fuller authentication.
- Stub endpoints will apply the rules in the loan service.
- Fine is calculated but collection and storage are handled elsewhere.
- Database persistence exists or is planned.
- Fine entity attributes are inferred, not defined in code.

## 9. Open Questions for Stakeholders
- How should users be authenticated and authorised?
- Should ISBNs be validated and duplicates prevented?
- Can a book be renewed or reserved?
- How are fines recorded, paid and waived? Do they block borrowing?
- Should a loan be prevented from being returned twice?
- What is the content of the return receipt, and is email mandatory?
- How are members registered and deactivated?
- Should members with overdue loans or unpaid fines be blocked?
- Are there expected volumes or performance targets?
- Can librarians edit or remove books?

## 10. Glossary
| Term | Definition |
|---|---|
| Loan | A record of a member borrowing a book, with due and return dates. |
| Active loan | A loan not yet returned. |
| Fine | Charge of 10 INR per day for late returns. |
| ISBN | International Standard Book Number identifying a book. |
| Librarian | Staff user with permission to manage the catalogue. |
| Copies available | Number of copies of a book currently on the shelf. |

## Appendix A. Module Overview
| Module | Purpose | Files |
|---|---|---|
| (root) | The README is a one-line title and description identifying the project as the backend for a small community library. It tells readers that the product is a server-side system for running a community library, but it does not describe any specific features or workflows. | 1 |
| app | This file is the entry point of the Library web application. It creates the application under the name "Library" and makes its book and loan features available to users at the /books and /loans web addresses. The rules and data behind those features live in other files. | 1 |
| app/api | Exposes the HTTP API layer of the library-app for book catalogue search, adding books, lending books to members, and returning loans. Access to librarian-only actions is controlled by a role check. Most endpoints are currently stubs, so the intended behaviour is only partly confirmed by working code. | 3 |
| app/models | Defines the core data records of the library application: books in the catalogue, library members (patrons and librarians), and loans that track which book a member borrowed and when it is due or was returned. It provides the basic shape of this information that the rest of the system relies on. | 1 |
| app/services | Core lending rules for the library: it decides whether a member may borrow a book, sets the return due date, and calculates late-return fines when a book comes back. It works with the book and member records supplied by the caller and does not store anything itself. | 1 |

## Appendix B. Analysis Notes
- 1 secret-looking files (.env, keys, ...) were never sent to the LLM.
