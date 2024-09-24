const express = require('express');
const bodyParser = require('body-parser');
const { Configuration, OpenAIApi } = require('openai');

const app = express();
const port = 3001;

app.use(bodyParser.json({ limit: '10mb' }));

const configuration = new Configuration({
    apiKey: process.env.AZURE_OPENAI_KEY,
});
const openai = new OpenAIApi(configuration);

app.post('/api/describe', async (req, res) => {
    const { image } = req.body;

    console.log('Received image data'); // Debugging line

    try {
        const response = await openai.createCompletion({
            model: 'text-davinci-003',
            prompt: `Describe the following image, but do not include any descriptions of people. Image data: ${image}`,
            max_tokens: 100,
        });

        console.log('OpenAI response:', response.data); // Debugging line

        const description = response.data.choices[0].text.trim();
        res.json({ description });
    } catch (error) {
        console.error('Error generating description:', error);
        res.status(500).json({ error: 'Failed to generate description' });
    }
});

app.listen(port, () => {
    console.log(`Server is running on http://localhost:${port}`);
});