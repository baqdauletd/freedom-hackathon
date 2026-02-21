export type TicketSegment = "Mass" | "VIP" | "Priority";
export type TicketType =
  | "Жалоба"
  | "Смена данных"
  | "Консультация"
  | "Претензия"
  | "Неработоспособность приложения"
  | "Мошеннические действия"
  | "Спам";

export type Sentiment = "Позитивный" | "Нейтральный" | "Негативный";
export type TicketLanguage = "KZ" | "ENG" | "RU";

export type Ticket = {
  id: string;
  gender: string;
  birthDate: string;
  description: string;
  attachments: string;
  segment: TicketSegment;
  country: string;
  region: string;
  city: string;
  street: string;
  house: string;
};

export type TicketAnalysis = {
  type: TicketType;
  sentiment: Sentiment;
  priority: number;
  language: TicketLanguage;
  summary: string;
  recommendation: string;
};

export type Manager = {
  id: string;
  name: string;
  role: string;
  office: string;
  skills: string[];
  currentLoad: number;
};

export type BusinessUnit = {
  office: string;
  address: string;
};

export type TicketAssignment = {
  ticketId: string;
  office: string;
  managerId: string;
  managerName: string;
  reasons: string[];
};

export type EnrichedTicket = Ticket & {
  analysis: TicketAnalysis;
  assignment: TicketAssignment;
};

export type ManagerWorkload = {
  managerId: string;
  managerName: string;
  office: string;
  currentLoad: number;
  assigned: number;
  total: number;
};
