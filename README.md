# Quizzie

## Overview
Quizzie is a robust application designed for creating, managing, and taking quizzes. It allows users to create custom quizzes and share them with others, offering both challenging and interactive experiences.

## Project Documentation

### Features
- User authentication and management
- Quiz creation and customization
- Multiple question types (multiple choice, true/false, short answer)
- Performance tracking and analytics

### Technologies Used
- Frontend: React.js
- Backend: Node.js with Express
- Database: MongoDB
- Authentication: JWT for secure login

## Setup Instructions

### Prerequisites
Ensure you have the following installed:
- Node.js 14+  
- npm or yarn
- MongoDB instance

### Installation Steps
1. Clone the repository:
   ```bash
   git clone https://github.com/OnlyArkMani/Quizzie.git
   cd Quizzie
   ```  
2. Install dependencies:
   ```bash
   npm install
   ```  
3. Set up environment variables:
   Create a `.env` file in the root of the project and add the following:
   ```bash
   PORT=5000
   MONGODB_URI=<your_mongodb_uri>
   JWT_SECRET=<your_jwt_secret>
   ```  
4. Run the application:
   ```bash
   npm start
   ```  
5. Open your browser and go to `http://localhost:5000` to access Quizzie.

## Architecture Overview

### Project Structure
```
Quizzie/
├── client/               # React frontend
│   ├── src/             # Source files
│   ├── public/          # Public assets
├── server/               # Express backend
│   ├── routes/          # API routes
│   ├── models/          # Mongoose models
│   └── config/          # Database and app configurations
└── .env                  # Environment variables
```  

### Interaction Flow
1. Users register and log in to access quizzes.
2. Users can create quizzes using a simple interface.
3. Participants can join quizzes via shared links.
4. Performance analytics are provided post-quiz.

## API Integration Guidelines

### API Endpoints
- `GET /api/quizzes` - Retrieve all quizzes
- `POST /api/quizzes` - Create a new quiz
- `POST /api/auth/login` - User login
- `GET /api/auth/user` - Get logged-in user details

### Example API Request
To retrieve all quizzes:
```bash
curl -X GET http://localhost:5000/api/quizzes
```

### Authentication
Use a JWT token obtained from logging in to access protected endpoints. Include it in the header of your requests:
```http
Authorization: Bearer <your_jwt_token>
```

## Contributing
Contributions are welcome! Please submit a pull request or open an issue for any improvements or bug fixes. 

## License
This project is licensed under the MIT License. See the LICENSE file for more details.
