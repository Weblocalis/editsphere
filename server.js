import express from 'express';
import path from 'path';
import fs from 'fs';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const app = express();
const PORT = process.env.PORT || 3000;
const HOST = '0.0.0.0';

// Serve jszip library
app.use('/vendor/jszip.min.js', (req, res) => {
  const jszipPath = path.join(__dirname, 'node_modules/jszip/dist/jszip.min.js');
  if (fs.existsSync(jszipPath)) {
    res.type('application/javascript').sendFile(jszipPath);
  } else {
    res.status(404).send('JSZip not found');
  }
});

// API to list bundled public domain masterpieces
app.get('/api/bundled-books', (req, res) => {
  try {
    const booksDir = path.join(__dirname, 'victor-hugo');
    if (!fs.existsSync(booksDir)) {
      return res.json([]);
    }
    const files = fs.readdirSync(booksDir);
    const books = files
      .filter(f => f.endsWith('.html') || f.endsWith('.htm'))
      .map(f => {
        const filePath = path.join(booksDir, f);
        const stats = fs.statSync(filePath);
        const cleanTitle = f.replace(/\.html?$/i, '');
        const isMhtml = f === 'napoleon-le-petit.html';
        return {
          filename: f,
          title: cleanTitle,
          size: stats.size,
          author: 'Victor Hugo',
          format: isMhtml ? 'MHTML' : 'HTML',
          url: `/victor-hugo/${encodeURIComponent(f)}`
        };
      })
      .sort((a, b) => a.title.localeCompare(b.title, 'fr'));
    res.json(books);
  } catch (err) {
    res.status(500).json({ error: String(err) });
  }
});

// Serve static assets from project root
app.use(express.static(__dirname));

// Fallback to index.html for any remaining route
app.get('*', (req, res) => {
  res.sendFile(path.join(__dirname, 'index.html'));
});

app.listen(PORT, HOST, () => {
  console.log(`EditSphere server listening at http://${HOST}:${PORT}`);
});
